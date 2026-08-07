from fastapi import APIRouter, HTTPException, Request, Response

from app.models.schemas import (
    AdminConfigRequest,
    AdminConfigResponse,
    AdminConfigStatusResponse,
    AdminUnlockRequest,
    AdminUnlockResponse,
)
from app.services.auth import (
    check_unlock_rate_limit,
    clear_admin_cookie,
    create_admin_token,
    get_admin_token_from_request,
    record_unlock_attempt,
    require_admin,
    set_admin_cookie,
    verify_admin_password,
    verify_admin_token,
)
from app.services.storage import storage

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/unlock", response_model=AdminUnlockResponse)
def admin_unlock(body: AdminUnlockRequest, request: Request, response: Response):
    client_ip = request.client.host if request.client else "unknown"
    check_unlock_rate_limit(client_ip)

    if not verify_admin_password(body.password):
        record_unlock_attempt(client_ip)
        return AdminUnlockResponse(success=False, message="Invalid password")

    token = create_admin_token()
    set_admin_cookie(response, token)
    return AdminUnlockResponse(success=True)


@router.post("/lock")
def admin_lock(response: Response):
    clear_admin_cookie(response)
    return {"success": True}


@router.get("/config/status", response_model=AdminConfigStatusResponse)
def admin_config_status(request: Request):
    configured = storage.is_admin_configured()
    output_configured = storage.is_output_sheet_configured()
    unlocked = verify_admin_token(get_admin_token_from_request(request))
    cfg = storage.get_admin_config()

    resp = AdminConfigStatusResponse(
        configured=configured,
        output_configured=output_configured,
        locked=not unlocked,
        sheet_url_masked="••••••••••" if configured else "",
        output_sheet_url_masked="••••••••••" if output_configured else "",
    )

    if unlocked:
        resp.sheet_url = cfg.get("sheet_url")
        resp.output_sheet_url = cfg.get("output_sheet_url")
        resp.docs_folder_id = cfg.get("docs_folder_id")
        resp.voice_output_dir = cfg.get("voice_output_dir")

    return resp


@router.post("/config", response_model=AdminConfigResponse)
def save_admin_config(body: AdminConfigRequest, request: Request, response: Response):
    require_admin(request)

    if not body.sheet_url.strip():
        raise HTTPException(status_code=400, detail="Input sheet URL is required")
    if not (body.output_sheet_url or "").strip():
        raise HTTPException(status_code=400, detail="Output sheet URL is required")

    storage.save_admin_config(
        body.sheet_url.strip(),
        docs_folder_id=body.docs_folder_id,
        output_sheet_url=body.output_sheet_url.strip(),
        voice_output_dir=body.voice_output_dir,
    )
    clear_admin_cookie(response)

    return AdminConfigResponse(success=True)


@router.get("/config", response_model=AdminConfigResponse)
def get_admin_config(request: Request):
    require_admin(request)
    cfg = storage.get_admin_config()
    return AdminConfigResponse(
        success=True,
        sheet_url=cfg.get("sheet_url"),
        output_sheet_url=cfg.get("output_sheet_url"),
        docs_folder_id=cfg.get("docs_folder_id"),
        voice_output_dir=cfg.get("voice_output_dir"),
    )
