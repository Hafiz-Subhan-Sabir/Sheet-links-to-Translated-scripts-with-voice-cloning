from typing import Optional

from fastapi import APIRouter, HTTPException

from app.models.schemas import SheetCreateRequest, SheetSessionResponse, SheetUseRequest
from app.services.auth import get_user_email
from app.services.sheet_workspace import bootstrap_sheets, create_and_use, session_payload, use_sheet

router = APIRouter(prefix="/api/sheets", tags=["sheets"])


def _to_response(payload: dict, email: Optional[str] = None) -> SheetSessionResponse:
    return SheetSessionResponse(
        email=payload.get("email") or email,
        input_url=payload.get("input_url"),
        output_url=payload.get("output_url"),
        input_history=payload.get("input_history") or [],
        output_history=payload.get("output_history") or [],
        created_input=bool(payload.get("created_input")),
        created_output=bool(payload.get("created_output")),
    )


@router.get("/session", response_model=SheetSessionResponse)
def get_sheet_session():
    email = get_user_email()
    if not email:
        raise HTTPException(status_code=401, detail="Google account not connected")
    return _to_response(session_payload(email), email)


@router.post("/bootstrap", response_model=SheetSessionResponse)
def bootstrap_sheet_session():
    try:
        return _to_response(bootstrap_sheets())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/use", response_model=SheetSessionResponse)
def use_existing_sheet(body: SheetUseRequest):
    try:
        payload = use_sheet(body.kind, body.url, title=body.title)
        email = get_user_email()
        return _to_response(payload, email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/create", response_model=SheetSessionResponse)
def create_sheet(body: SheetCreateRequest):
    try:
        payload = create_and_use(body.kind)
        email = get_user_email()
        return _to_response(payload, email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
