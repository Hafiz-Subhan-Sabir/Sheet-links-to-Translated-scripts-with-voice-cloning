import logging
from dataclasses import dataclass
from typing import Optional

from googleapiclient.discovery import build

from app.config import get_settings
from app.constants import (
    BATCH_STATUS_DONE,
    BATCH_STATUS_FAILED,
    BATCH_STATUS_PENDING,
    BATCH_STATUS_PROCESSING,
    INPUT_SHEET_HEADERS,
)
from app.services.auth import get_credentials
from app.services.google_integrations import extract_spreadsheet_id
from app.services.storage import storage

logger = logging.getLogger(__name__)


def _sheets_service():
    creds = get_credentials()
    if not creds:
        raise ValueError("Google account not connected")
    return build("sheets", "v4", credentials=creds, cache_discovery=False)

VALID_STATUSES = {
    BATCH_STATUS_PENDING,
    BATCH_STATUS_PROCESSING,
    BATCH_STATUS_DONE,
    BATCH_STATUS_FAILED,
}

_STATUS_ALIASES: dict[str, str] = {
    "complete": BATCH_STATUS_DONE,
    "completed": BATCH_STATUS_DONE,
    "finished": BATCH_STATUS_DONE,
    "success": BATCH_STATUS_DONE,
    "fail": BATCH_STATUS_FAILED,
    "error": BATCH_STATUS_FAILED,
    "running": BATCH_STATUS_PROCESSING,
    "in progress": BATCH_STATUS_PROCESSING,
    "in_progress": BATCH_STATUS_PROCESSING,
    "queued": BATCH_STATUS_PENDING,
    "queue": BATCH_STATUS_PENDING,
}


def normalize_queue_status(raw: str) -> str:
    s = raw.strip().lower()
    if not s:
        return BATCH_STATUS_PENDING
    if s in VALID_STATUSES:
        return s
    return _STATUS_ALIASES.get(s, BATCH_STATUS_PENDING)


@dataclass
class QueueRow:
    row_index: int
    program_title: str
    video_path: str
    status: str
    error: str


def resolve_input_sheet_url() -> Optional[str]:
    settings = get_settings()
    env_url = settings.input_sheet_url.strip()
    if env_url:
        return env_url
    admin_url = (storage.get_admin_config().get("sheet_url") or "").strip()
    return admin_url or None


def is_input_sheet_configured() -> bool:
    return bool(resolve_input_sheet_url())


def _sheet_tab_name(spreadsheet_id: str) -> str:
    settings = get_settings()
    if settings.input_sheet_tab.strip():
        return settings.input_sheet_tab.strip()
    meta = (
        _sheets_service()
        .spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="sheets.properties.title")
        .execute()
    )
    sheets = meta.get("sheets", [])
    if not sheets:
        raise ValueError("Spreadsheet has no tabs")
    return sheets[0]["properties"]["title"]


def _normalize_header(value: str) -> str:
    return value.strip().lower().replace("_", " ")


# Canonical column keys → accepted header labels (normalized)
_COLUMN_ALIASES: dict[str, list[str]] = {
    "program title": [
        "program title",
        "programme title",
        "video name",
        "title",
        "name",
    ],
    "video path": [
        "video path",
        "path",
        "video",
        "file path",
        "filepath",
        "video url",
        "url",
        "link",
    ],
    "status": ["status"],
    "error": ["error", "errors", "error message", "error messages"],
}


def _column_map(header_row: list[str]) -> dict[str, int]:
    normalized: dict[str, int] = {}
    for idx, cell in enumerate(header_row):
        key = _normalize_header(str(cell))
        if key:
            normalized[key] = idx

    resolved: dict[str, int] = {}
    missing: list[str] = []
    for canonical, aliases in _COLUMN_ALIASES.items():
        found = next((normalized[a] for a in aliases if a in normalized), None)
        if found is None:
            missing.append(INPUT_SHEET_HEADERS[list(_COLUMN_ALIASES.keys()).index(canonical)])
        else:
            resolved[canonical] = found

    if missing:
        raise ValueError(
            f"Input sheet missing columns: {', '.join(missing)}. "
            f"Expected headers: {' | '.join(INPUT_SHEET_HEADERS)}"
        )
    return resolved


def read_queue(*, include_non_pending: bool = True) -> list[QueueRow]:
    sheet_url = resolve_input_sheet_url()
    if not sheet_url:
        raise ValueError("Input sheet URL is not configured")

    spreadsheet_id = extract_spreadsheet_id(sheet_url)
    tab = _sheet_tab_name(spreadsheet_id)
    result = (
        _sheets_service()
        .spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"'{tab}'!A:D")
        .execute()
    )
    values = result.get("values", [])
    if not values:
        return []

    col = _column_map(values[0])
    rows: list[QueueRow] = []
    for i, raw in enumerate(values[1:], start=2):
        padded = raw + [""] * (4 - len(raw))
        status = normalize_queue_status(str(padded[col["status"]]))
        if not include_non_pending and status != BATCH_STATUS_PENDING:
            continue
        program_title = str(padded[col["program title"]]).strip()
        video_path = str(padded[col["video path"]]).strip()
        if not program_title and not video_path:
            continue
        rows.append(
            QueueRow(
                row_index=i,
                program_title=program_title,
                video_path=video_path,
                status=status,
                error=str(padded[col["error"]]).strip(),
            )
        )
    return rows


def update_row_status(row_index: int, status: str, error: str = "") -> None:
    """Update Status and Error/Errors columns in the input sheet immediately."""
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}")

    sheet_url = resolve_input_sheet_url()
    if not sheet_url:
        raise ValueError("Input sheet URL is not configured")

    spreadsheet_id = extract_spreadsheet_id(sheet_url)
    tab = _sheet_tab_name(spreadsheet_id)

    header_result = (
        _sheets_service()
        .spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"'{tab}'!A1:D1")
        .execute()
    )
    headers = header_result.get("values", [[]])[0]
    col = _column_map(headers)

    status_col = chr(ord("A") + col["status"])
    error_col = chr(ord("A") + col["error"])
    _sheets_service().spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "valueInputOption": "USER_ENTERED",
            "data": [
                {"range": f"'{tab}'!{status_col}{row_index}", "values": [[status]]},
                {"range": f"'{tab}'!{error_col}{row_index}", "values": [[error]]},
            ],
        },
    ).execute()
