from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.models.schemas import AuthStatusResponse
from app.services.auth import (
    exchange_code,
    get_authorization_url,
    get_oauth_verifier,
    get_user_email,
    remove_oauth_state,
    store_oauth_state,
)
from app.services.storage import storage

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _frontend_base_url() -> str:
    """OAuth return URL — always port 3000 for local dev."""
    url = get_settings().frontend_url.rstrip("/")
    if "localhost" in url or "127.0.0.1" in url:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url if "://" in url else f"http://{url}")
        host = parsed.hostname or "localhost"
        scheme = parsed.scheme or "http"
        url = urlunparse((scheme, f"{host}:3000", "", "", "", ""))
    return url


@router.get("/google")
def google_auth_start():
    settings = get_settings()
    if not settings.google_client_id.strip() or not settings.google_client_secret.strip():
        # Stay in the app UI instead of dumping a raw API error page
        msg = (
            "Google+OAuth+not+configured.+Add+GOOGLE_CLIENT_ID+and+GOOGLE_CLIENT_SECRET+"
            "to+backend/.env+then+restart+the+backend."
        )
        return RedirectResponse(f"{_frontend_base_url()}?auth=error&message={msg}")
    url, state, code_verifier = get_authorization_url()
    store_oauth_state(state, code_verifier)
    return RedirectResponse(url)


@router.get("/google/callback")
def google_auth_callback(
    state: str = Query(...),
    code: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
):
    settings = get_settings()

    if error:
        if error == "access_denied":
            msg = (
                "Google sign-in was cancelled or this Gmail is not allowed yet. "
                "In Google Cloud Console → OAuth consent screen → Test users, add this exact email, "
                "save, wait a minute, then try again and pick that account."
            )
        else:
            detail = error_description or error
            msg = f"Google login failed: {detail}"
        safe = msg.replace(" ", "+")
        return RedirectResponse(f"{_frontend_base_url()}?auth=error&message={safe}")

    if not code:
        return RedirectResponse(
            f"{_frontend_base_url()}?auth=error&message=Missing+authorization+code.+Click+Connect+Google+again."
        )

    code_verifier = get_oauth_verifier(state)
    if not code_verifier:
        return RedirectResponse(
            f"{_frontend_base_url()}?auth=error&message=Session+expired.+Click+Connect+Google+Account+again."
        )

    try:
        tokens = exchange_code(code, state, code_verifier)
        storage.save_google_tokens(tokens)
        remove_oauth_state(state)
    except Exception as e:
        msg = str(e).replace(" ", "+")
        return RedirectResponse(f"{_frontend_base_url()}?auth=error&message={msg}")

    return RedirectResponse(f"{_frontend_base_url()}?auth=success")


@router.get("/status", response_model=AuthStatusResponse)
def auth_status():
    from app.services.input_sheet import is_input_sheet_configured, resolve_input_sheet_url

    settings = get_settings()
    email = get_user_email()
    sheet_url = resolve_input_sheet_url() if is_input_sheet_configured() else None
    return AuthStatusResponse(
        connected=email is not None,
        email=email,
        sheet_ready=is_input_sheet_configured(),
        sheet_url=sheet_url,
        oauth_configured=bool(
            settings.google_client_id.strip() and settings.google_client_secret.strip()
        ),
    )


@router.post("/refresh-registry")
def refresh_registry_sheet():
    """Force-create a new registry sheet for the connected Google account."""
    if not get_user_email():
        raise HTTPException(status_code=401, detail="Google account not connected")
    from app.services.google_integrations import recreate_registry_spreadsheet

    sheet_url = recreate_registry_spreadsheet()
    return {"success": True, "sheet_url": sheet_url}


@router.post("/disconnect")
def disconnect_google():
    storage.clear_google_tokens()
    return {"success": True}
