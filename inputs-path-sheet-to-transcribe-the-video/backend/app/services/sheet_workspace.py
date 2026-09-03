"""Per-user input/output Google Sheets: recent cache, paste URL, or auto-create."""

from __future__ import annotations

import logging
import threading
from typing import Any, Literal, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import get_settings
from app.constants import INPUT_SHEET_HEADERS, OUTPUT_SHEET_HEADERS
from app.services.auth import get_credentials, get_user_email
from app.services.google_integrations import extract_spreadsheet_id
from app.services.storage import storage

logger = logging.getLogger(__name__)

SheetKind = Literal["input", "output"]

_INPUT_TITLE = "VoltScript — Video list"
_OUTPUT_TITLE = "VoltScript — Transcripts"

_bootstrap_lock = threading.Lock()


def _require_email() -> str:
    email = get_user_email()
    if not email:
        raise ValueError("Google account not connected")
    return email


def _sheets_service():
    creds = get_credentials()
    if not creds:
        raise ValueError("Google account not connected")
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def session_payload(email: Optional[str] = None) -> dict[str, Any]:
    key = (email or get_user_email() or "").strip().lower()
    session = storage.get_sheet_session(key) if key else {
        "input_url": None,
        "output_url": None,
        "input_history": [],
        "output_history": [],
    }
    settings = get_settings()
    if not session.get("input_url") and settings.input_sheet_url.strip():
        session["input_url"] = settings.input_sheet_url.strip()
    if not session.get("output_url") and settings.output_sheet_url.strip():
        session["output_url"] = settings.output_sheet_url.strip()
    return session


def spreadsheet_title(sheet_url: str) -> str:
    spreadsheet_id = extract_spreadsheet_id(sheet_url)
    meta = (
        _sheets_service()
        .spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="properties.title")
        .execute()
    )
    return (meta.get("properties") or {}).get("title") or spreadsheet_id


def create_spreadsheet(kind: SheetKind) -> dict[str, str]:
    title = _INPUT_TITLE if kind == "input" else _OUTPUT_TITLE
    headers = list(INPUT_SHEET_HEADERS if kind == "input" else OUTPUT_SHEET_HEADERS)
    tab = "Queue" if kind == "input" else "Results"
    service = _sheets_service()
    try:
        spreadsheet = (
            service.spreadsheets()
            .create(
                body={
                    "properties": {"title": title},
                    "sheets": [{"properties": {"title": tab}}],
                }
            )
            .execute()
        )
    except HttpError as e:
        raise ValueError("Couldn’t create a Google Sheet. Reconnect Google and try again.") from e
    spreadsheet_id = spreadsheet["spreadsheetId"]
    from app.services.output_sheet import _col_letter

    end_col = _col_letter(max(0, len(headers) - 1))
    try:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{tab}'!A1:{end_col}1",
            valueInputOption="USER_ENTERED",
            body={"values": [headers]},
        ).execute()
    except HttpError as e:
        raise ValueError("Google Sheets create failed. Reconnect Google and try again.") from e
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
    return {"url": url, "title": title}


def use_sheet(kind: SheetKind, url: str, *, title: str = "") -> dict[str, Any]:
    email = _require_email()
    cleaned = (url or "").strip()
    if not cleaned:
        raise ValueError("Paste a Google Sheet link")
    extract_spreadsheet_id(cleaned)
    label = title.strip()
    try:
        label = label or spreadsheet_title(cleaned)
    except HttpError as e:
        status = getattr(getattr(e, "resp", None), "status", None)
        if status in (403, 404):
            raise ValueError(
                "Couldn’t open that spreadsheet. Share it with the connected Google account, or create a new one."
            ) from e
        raise ValueError("That doesn’t look like a Google Sheet this account can open.") from e
    except ValueError:
        raise
    except Exception as e:
        logger.warning("Could not read sheet title: %s", e)
        label = label or cleaned

    if kind == "input":
        from app.services.input_sheet import ensure_input_headers

        storage.remember_sheet(email, kind="input", url=cleaned, title=label)
        ensure_input_headers()
    else:
        from app.services.output_sheet import ensure_output_headers

        storage.remember_sheet(email, kind="output", url=cleaned, title=label)
        ensure_output_headers()
    return session_payload(email)


def create_and_use(kind: SheetKind) -> dict[str, Any]:
    created = create_spreadsheet(kind)
    return use_sheet(kind, created["url"], title=created["title"])


def bootstrap_sheets() -> dict[str, Any]:
    """
    Restore last-used sheets for this Google account.
    If none exist, create a new input and output spreadsheet.
    """
    email = _require_email()
    with _bootstrap_lock:
        session = session_payload(email)
        created_input = False
        created_output = False

        if not session.get("input_url"):
            history = session.get("input_history") or []
            if history and history[0].get("url"):
                use_sheet("input", history[0]["url"], title=history[0].get("title") or "")
            else:
                create_and_use("input")
                created_input = True

        session = session_payload(email)
        if not session.get("output_url"):
            history = session.get("output_history") or []
            if history and history[0].get("url"):
                use_sheet("output", history[0]["url"], title=history[0].get("title") or "")
            else:
                create_and_use("output")
                created_output = True

        session = session_payload(email)
        session["created_input"] = created_input
        session["created_output"] = created_output
        session["email"] = email
        return session
