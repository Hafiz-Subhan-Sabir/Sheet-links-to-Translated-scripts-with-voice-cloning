import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import jwt
from fastapi import HTTPException, Request, Response
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from app.config import get_settings
from app.services.storage import storage

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

_unlock_attempts: dict[str, list[datetime]] = {}
_oauth_pending_path = None


def _oauth_pending_file():
    global _oauth_pending_path
    if _oauth_pending_path is None:
        settings = get_settings()
        _oauth_pending_path = Path(settings.data_dir) / "oauth_pending.json"
        _oauth_pending_path.parent.mkdir(parents=True, exist_ok=True)
    return _oauth_pending_path


def _load_oauth_pending() -> dict[str, str]:
    path = _oauth_pending_file()
    if not path.exists():
        return {}
    try:
        import json

        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_oauth_pending(data: dict[str, str]) -> None:
    import json

    _oauth_pending_file().write_text(json.dumps(data, indent=2), encoding="utf-8")


def store_oauth_state(state: str, code_verifier: str) -> None:
    pending = _load_oauth_pending()
    pending[state] = code_verifier
    _save_oauth_pending(pending)


def get_oauth_verifier(state: str) -> str | None:
    pending = _load_oauth_pending()
    return pending.get(state)


def remove_oauth_state(state: str) -> None:
    pending = _load_oauth_pending()
    pending.pop(state, None)
    _save_oauth_pending(pending)


def pop_oauth_state(state: str) -> str | None:
    """Deprecated: use get_oauth_verifier + remove_oauth_state on success."""
    return get_oauth_verifier(state)


def _extract_code_verifier(flow: Flow) -> str:
    verifier = getattr(flow, "code_verifier", None)
    if verifier:
        return verifier
    session = getattr(flow, "oauth2session", None)
    if session is not None:
        verifier = getattr(session, "code_verifier", None) or getattr(session, "_code_verifier", None)
        if verifier:
            return verifier
    return ""


def _client_config() -> dict:
    settings = get_settings()
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }


def create_oauth_flow(state: Optional[str] = None) -> Flow:
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, state=state)
    settings = get_settings()
    flow.redirect_uri = settings.google_redirect_uri
    return flow


def get_authorization_url() -> tuple[str, str, str]:
    flow = create_oauth_flow()
    state = secrets.token_urlsafe(32)
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="select_account consent",
        state=state,
    )
    code_verifier = _extract_code_verifier(flow)
    if not code_verifier:
        raise RuntimeError("Failed to generate OAuth PKCE code verifier")
    return url, state, code_verifier


def exchange_code(code: str, state: str, code_verifier: str) -> dict:
    flow = create_oauth_flow(state=state)
    if not code_verifier:
        raise ValueError("Missing PKCE code verifier for this login session")
    flow.code_verifier = code_verifier
    flow.oauth2session.code_verifier = code_verifier
    if hasattr(flow.oauth2session, "_code_verifier"):
        flow.oauth2session._code_verifier = code_verifier
    flow.fetch_token(code=code)
    creds = flow.credentials
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
    }


def get_credentials() -> Optional[Credentials]:
    tokens = storage.get_google_tokens()
    if not tokens:
        return None
    creds = Credentials(
        token=tokens.get("token"),
        refresh_token=tokens.get("refresh_token"),
        token_uri=tokens.get("token_uri"),
        client_id=tokens.get("client_id"),
        client_secret=tokens.get("client_secret"),
        scopes=tokens.get("scopes"),
    )
    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request

        try:
            creds.refresh(Request())
            tokens["token"] = creds.token
            storage.save_google_tokens(tokens)
        except Exception:
            storage.clear_google_tokens()
            return None
    return creds


def get_user_email() -> Optional[str]:
    creds = get_credentials()
    if not creds:
        return None
    try:
        from googleapiclient.discovery import build

        service = build("oauth2", "v2", credentials=creds)
        info = service.userinfo().get().execute()
        return info.get("email")
    except Exception:
        storage.clear_google_tokens()
        return None


def create_admin_token() -> str:
    settings = get_settings()
    payload = {
        "admin": True,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.admin_session_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def verify_admin_token(token: Optional[str]) -> bool:
    if not token:
        return False
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return payload.get("admin") is True
    except jwt.PyJWTError:
        return False


def get_admin_token_from_request(request: Request) -> Optional[str]:
    return request.cookies.get("admin_session")


def require_admin(request: Request) -> None:
    token = get_admin_token_from_request(request)
    if not verify_admin_token(token):
        raise HTTPException(status_code=403, detail="Admin session required")


def set_admin_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key="admin_session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.admin_session_minutes * 60,
        secure=False,
    )


def clear_admin_cookie(response: Response) -> None:
    response.delete_cookie("admin_session")


def check_unlock_rate_limit(client_ip: str) -> None:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    window = timedelta(minutes=settings.unlock_window_minutes)
    attempts = _unlock_attempts.get(client_ip, [])
    attempts = [t for t in attempts if now - t < window]
    _unlock_attempts[client_ip] = attempts
    if len(attempts) >= settings.max_unlock_attempts:
        raise HTTPException(status_code=429, detail="Too many unlock attempts. Try again later.")


def record_unlock_attempt(client_ip: str) -> None:
    now = datetime.now(timezone.utc)
    _unlock_attempts.setdefault(client_ip, []).append(now)


def verify_admin_password(password: str) -> bool:
    settings = get_settings()
    return secrets.compare_digest(password, settings.admin_password)
