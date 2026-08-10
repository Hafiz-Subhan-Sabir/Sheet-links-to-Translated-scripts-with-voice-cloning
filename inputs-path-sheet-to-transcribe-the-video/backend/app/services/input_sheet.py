import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

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

_TAB_TTL_SEC = 600.0
_QUEUE_TTL_SEC = 3.0
_tab_cache: dict[str, tuple[str, float]] = {}
_col_cache: dict[str, dict[str, int]] = {}
_queue_cache: dict[str, tuple[float, list["QueueRow"]]] = {}


def _sheets_service():
    creds = get_credentials()
    if not creds:
        raise ValueError("Google account not connected")
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _execute_sheets(request: Any, *, what: str = "Sheets API"):
    """Run a Sheets request with backoff on per-user read quota (60/min)."""
    delay = 2.0
    last: Optional[Exception] = None
    for attempt in range(5):
        try:
            return request.execute()
        except HttpError as e:
            last = e
            status = getattr(getattr(e, "resp", None), "status", None)
            if status != 429 or attempt == 4:
                if status == 429:
                    raise ValueError(
                        "Google Sheets rate limit hit (60 reads/min). "
                        "Wait about a minute, then click Refresh."
                    ) from e
                raise
            logger.warning("%s rate-limited (429); retry in %.0fs", what, delay)
            time.sleep(delay)
            delay = min(delay * 2, 20.0)
    raise last  # type: ignore[misc]


def _invalidate_queue_cache() -> None:
    _queue_cache.clear()

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
    now = time.monotonic()
    cached = _tab_cache.get(spreadsheet_id)
    if cached and now - cached[1] < _TAB_TTL_SEC:
        return cached[0]
    meta = _execute_sheets(
        _sheets_service()
        .spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="sheets.properties.title"),
        what="input tab lookup",
    )
    sheets = meta.get("sheets", [])
    if not sheets:
        raise ValueError("Spreadsheet has no tabs")
    title = sheets[0]["properties"]["title"]
    _tab_cache[spreadsheet_id] = (title, now)
    return title


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


def _soft_column_map(header_row: list[str]) -> dict[str, int]:
    """Map known header aliases without requiring every column."""
    normalized: dict[str, int] = {}
    for idx, cell in enumerate(header_row):
        key = _normalize_header(str(cell))
        if key:
            normalized[key] = idx

    resolved: dict[str, int] = {}
    for canonical, aliases in _COLUMN_ALIASES.items():
        found = next((normalized[a] for a in aliases if a in normalized), None)
        if found is not None:
            resolved[canonical] = found
    return resolved


def _column_map(header_row: list[str]) -> dict[str, int]:
    resolved = _soft_column_map(header_row)
    missing: list[str] = []
    for canonical in _COLUMN_ALIASES:
        if canonical not in resolved:
            missing.append(INPUT_SHEET_HEADERS[list(_COLUMN_ALIASES.keys()).index(canonical)])
    if missing:
        raise ValueError(
            f"Input sheet missing columns: {', '.join(missing)}. "
            f"Expected headers: {' | '.join(INPUT_SHEET_HEADERS)}"
        )
    return resolved


def _cell_looks_like_path_or_url(value: str) -> bool:
    v = value.strip().strip('"').strip("'")
    if not v:
        return False
    lower = v.lower()
    if lower.startswith(("http://", "https://", "www.", "file://")):
        return True
    if any(d in lower for d in ("youtube.com/", "youtu.be/", "vimeo.com/", "tiktok.com/")):
        return True
    if re.match(r"^[a-zA-Z]:\\", v) or v.startswith("\\\\") or (v.startswith("/") and not v.startswith("//")):
        return True
    if any(lower.endswith(ext) for ext in (".mp4", ".mkv", ".mov", ".webm", ".avi", ".mp3", ".wav", ".m4a")):
        return True
    return False


def default_video_name(path: str, index: int) -> str:
    """Derive a display name from a URL/path when the sheet has no title column."""
    raw = (path or "").strip()
    if not raw:
        return f"Video {index}"
    try:
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        host = (parsed.netloc or "").lower()
        if "youtu.be" in host:
            slug = parsed.path.strip("/").split("/")[0]
            if slug:
                return slug
        if "youtube.com" in host:
            qs = parse_qs(parsed.query)
            vid = (qs.get("v") or [None])[0]
            if vid:
                return vid
            parts = [p for p in parsed.path.split("/") if p]
            if parts and parts[0] in ("shorts", "embed", "live", "v") and len(parts) > 1:
                return parts[1]
        path_part = parsed.path.rstrip("/").split("/")[-1] if parsed.path else ""
        if path_part and path_part not in ("watch",):
            return path_part
    except Exception:
        pass
    name = re.split(r"[\\/]", raw)[-1].strip()
    if name and name != raw:
        return name
    return f"Video {index}"


def _cell(row: list, index: Optional[int]) -> str:
    if index is None or index < 0 or index >= len(row):
        return ""
    return str(row[index]).strip()


def plan_normalized_sheet(values: list[list]) -> Optional[list[list[str]]]:
    """
    Return a rewritten sheet (headers + rows) when the input sheet needs managing.
    Returns None when the sheet already has the required columns.
    """
    if not values:
        return [list(INPUT_SHEET_HEADERS)]

    header = [str(c) for c in values[0]]
    soft = _soft_column_map(header)
    required = {"program title", "video path", "status", "error"}
    if required.issubset(soft.keys()):
        return None

    # Bare URL/path list (no header row) — common when users paste links in column A.
    first = str(header[0]).strip() if header else ""
    if not soft and _cell_looks_like_path_or_url(first):
        new_values: list[list[str]] = [list(INPUT_SHEET_HEADERS)]
        for i, raw in enumerate(values, start=1):
            path = str(raw[0]).strip() if raw else ""
            if not path:
                continue
            new_values.append(
                [default_video_name(path, i), path, BATCH_STATUS_PENDING, ""]
            )
        return new_values

    # Partial / wrong headers — preserve what we can into canonical columns.
    data_rows = values[1:] if soft else values
    title_i = soft.get("program title")
    path_i = soft.get("video path")
    status_i = soft.get("status")
    error_i = soft.get("error")

    if path_i is None and title_i is None:
        path_i = 0

    new_values = [list(INPUT_SHEET_HEADERS)]
    for i, raw in enumerate(data_rows, start=1):
        padded = list(raw) if raw else []
        path = _cell(padded, path_i)
        title = _cell(padded, title_i)
        if not path and title and _cell_looks_like_path_or_url(title):
            path, title = title, ""
        if not path and not title:
            for cell in padded:
                text = str(cell).strip()
                if _cell_looks_like_path_or_url(text):
                    path = text
                    break
        if not path and not title:
            continue
        if not path:
            path = title
            title = ""
        if not title:
            title = default_video_name(path, i)
        status = (
            normalize_queue_status(_cell(padded, status_i))
            if status_i is not None
            else BATCH_STATUS_PENDING
        )
        error = _cell(padded, error_i) if error_i is not None else ""
        new_values.append([title, path, status, error])

    return new_values


def _write_normalized_sheet(
    service: Any,
    spreadsheet_id: str,
    tab: str,
    values: list[list],
    planned: list[list[str]],
) -> None:
    logger.info(
        "Normalizing input sheet headers/rows (%s data rows)",
        max(0, len(planned) - 1),
    )
    if values:
        _execute_sheets(
            service.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=f"'{tab}'!A:Z",
                body={},
            ),
            what="input sheet clear",
        )
    _execute_sheets(
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{tab}'!A1",
            valueInputOption="USER_ENTERED",
            body={"values": planned},
        ),
        what="input sheet write",
    )
    _invalidate_queue_cache()
    _col_cache[spreadsheet_id] = _column_map(planned[0])


def ensure_input_headers() -> None:
    """
    Create/repair input sheet columns automatically.
    Supports bare YouTube URL lists in column A with no headers.
    """
    sheet_url = resolve_input_sheet_url()
    if not sheet_url:
        raise ValueError("Input sheet URL is not configured")

    spreadsheet_id = extract_spreadsheet_id(sheet_url)
    tab = _sheet_tab_name(spreadsheet_id)
    service = _sheets_service()
    result = _execute_sheets(
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"'{tab}'!A:Z"),
        what="input sheet read",
    )
    values = result.get("values", [])
    planned = plan_normalized_sheet(values)
    if planned is None:
        if values:
            _col_cache[spreadsheet_id] = _column_map(values[0])
        return
    _write_normalized_sheet(service, spreadsheet_id, tab, values, planned)


def _parse_queue_rows(values: list[list], *, include_non_pending: bool) -> list[QueueRow]:
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
        if not program_title and video_path:
            program_title = default_video_name(video_path, i - 1)
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


def read_queue(*, include_non_pending: bool = True) -> list[QueueRow]:
    """One Sheets read per call (plus rare normalize write). Short TTL cache for polling."""
    sheet_url = resolve_input_sheet_url()
    if not sheet_url:
        raise ValueError("Input sheet URL is not configured")

    cache_key = "all" if include_non_pending else "pending"
    now = time.monotonic()
    cached = _queue_cache.get(cache_key)
    if cached and now - cached[0] < _QUEUE_TTL_SEC:
        return list(cached[1])

    spreadsheet_id = extract_spreadsheet_id(sheet_url)
    tab = _sheet_tab_name(spreadsheet_id)
    service = _sheets_service()
    result = _execute_sheets(
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"'{tab}'!A:Z"),
        what="input queue read",
    )
    values = result.get("values", [])
    planned = plan_normalized_sheet(values)
    if planned is not None:
        _write_normalized_sheet(service, spreadsheet_id, tab, values, planned)
        values = planned
    elif values:
        try:
            _col_cache[spreadsheet_id] = _column_map(values[0])
        except ValueError:
            pass

    rows = _parse_queue_rows(values, include_non_pending=include_non_pending)
    _queue_cache[cache_key] = (now, list(rows))
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
    col = _col_cache.get(spreadsheet_id)
    if not col:
        header_result = _execute_sheets(
            _sheets_service()
            .spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=f"'{tab}'!A1:D1"),
            what="input header read",
        )
        headers = header_result.get("values", [[]])[0]
        try:
            col = _column_map(headers)
        except ValueError:
            ensure_input_headers()
            col = _col_cache.get(spreadsheet_id) or _column_map(
                _execute_sheets(
                    _sheets_service()
                    .spreadsheets()
                    .values()
                    .get(spreadsheetId=spreadsheet_id, range=f"'{tab}'!A1:D1"),
                    what="input header reread",
                ).get("values", [[]])[0]
            )
        _col_cache[spreadsheet_id] = col

    status_col = chr(ord("A") + col["status"])
    error_col = chr(ord("A") + col["error"])
    _execute_sheets(
        _sheets_service().spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "valueInputOption": "USER_ENTERED",
                "data": [
                    {"range": f"'{tab}'!{status_col}{row_index}", "values": [[status]]},
                    {"range": f"'{tab}'!{error_col}{row_index}", "values": [[error]]},
                ],
            },
        ),
        what="input status update",
    )
    _invalidate_queue_cache()
