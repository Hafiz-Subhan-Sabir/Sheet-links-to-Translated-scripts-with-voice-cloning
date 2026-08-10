"""Output Google Sheet — stores transcribed/translated results."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import get_settings
from app.constants import (
    BATCH_STATUS_MARKED_DONE,
    BATCH_STATUS_VOICE_DONE,
    BATCH_STATUS_VOICE_READY,
    OUTPUT_SHEET_HEADERS,
    SHEET_CELL_MAX,
)
from app.services.auth import get_credentials
from app.services.google_integrations import extract_spreadsheet_id
from app.services.storage import storage

logger = logging.getLogger(__name__)

_TAB_TTL_SEC = 600.0
_tab_cache: dict[str, tuple[str, float]] = {}
_headers_ready: set[str] = set()


def _sheets_service():
    creds = get_credentials()
    if not creds:
        raise ValueError("Google account not connected")
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _execute_sheets(request: Any, *, what: str = "Sheets API"):
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


def resolve_output_sheet_url() -> Optional[str]:
    settings = get_settings()
    env_url = settings.output_sheet_url.strip()
    if env_url:
        return env_url
    return (storage.get_admin_config().get("output_sheet_url") or "").strip() or None


def is_output_sheet_configured() -> bool:
    return bool(resolve_output_sheet_url())


def _sheet_tab_name(spreadsheet_id: str) -> str:
    settings = get_settings()
    if settings.output_sheet_tab.strip():
        return settings.output_sheet_tab.strip()
    now = time.monotonic()
    cached = _tab_cache.get(spreadsheet_id)
    if cached and now - cached[1] < _TAB_TTL_SEC:
        return cached[0]
    meta = _execute_sheets(
        _sheets_service()
        .spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="sheets.properties.title"),
        what="output tab lookup",
    )
    sheets = meta.get("sheets", [])
    if not sheets:
        raise ValueError("Output spreadsheet has no tabs")
    title = sheets[0]["properties"]["title"]
    _tab_cache[spreadsheet_id] = (title, now)
    return title


def _col_letter(index: int) -> str:
    """0-based column index → A, B, … Z, AA, …"""
    result = ""
    n = index
    while True:
        result = chr(ord("A") + (n % 26)) + result
        n = n // 26 - 1
        if n < 0:
            break
    return result


def truncate_for_sheet(text: str, max_chars: int = SHEET_CELL_MAX) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    note = "\n\n[Truncated for Google Sheets cell limit — see Google Docs Link for full text.]"
    return text[: max_chars - len(note)] + note


def ensure_output_headers() -> None:
    """Create header row if the output sheet is empty or missing expected columns."""
    sheet_url = resolve_output_sheet_url()
    if not sheet_url:
        raise ValueError("Output sheet URL is not configured")

    spreadsheet_id = extract_spreadsheet_id(sheet_url)
    if spreadsheet_id in _headers_ready:
        return

    tab = _sheet_tab_name(spreadsheet_id)
    result = _execute_sheets(
        _sheets_service()
        .spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"'{tab}'!1:1"),
        what="output header read",
    )
    values = result.get("values", [])
    if values and values[0]:
        existing = [str(c).strip().lower() for c in values[0]]
        expected = [h.lower() for h in OUTPUT_SHEET_HEADERS]
        if existing[: len(expected)] == expected or "video name" in existing:
            _headers_ready.add(spreadsheet_id)
            return

    end_col = _col_letter(len(OUTPUT_SHEET_HEADERS) - 1)
    _execute_sheets(
        _sheets_service().spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{tab}'!A1:{end_col}1",
            valueInputOption="USER_ENTERED",
            body={"values": [OUTPUT_SHEET_HEADERS]},
        ),
        what="output header write",
    )
    _headers_ready.add(spreadsheet_id)


@dataclass
class OutputRowData:
    video_name: str
    source_video: str
    english: str
    british: str
    american: str
    translations: dict[str, str]  # display name → text
    category: str
    video_length: str
    date_transcribed: str
    detected_language: str
    docs_link: str
    status: str = BATCH_STATUS_VOICE_READY
    voice_name: str = ""
    voice_directory: str = ""
    voice_notes: str = ""
    error: str = ""


@dataclass
class OutputRow:
    row_index: int
    video_name: str
    source_video: str = ""
    category: str = ""
    video_length: str = ""
    date_transcribed: str = ""
    docs_link: str = ""
    status: str = ""
    voice_name: str = ""
    voice_directory: str = ""
    voice_notes: str = ""
    error: str = ""
    cells: dict[str, str] = field(default_factory=dict)


def _header_index_map(headers: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for i, h in enumerate(headers):
        key = str(h).strip().lower()
        if key:
            mapping[key] = i
    return mapping


def append_output_row(data: OutputRowData) -> int:
    """Append one result row. Returns the 1-based row index."""
    ensure_output_headers()
    sheet_url = resolve_output_sheet_url()
    assert sheet_url
    spreadsheet_id = extract_spreadsheet_id(sheet_url)
    tab = _sheet_tab_name(spreadsheet_id)

    trans = data.translations
    row = [
        data.video_name,
        data.source_video,
        truncate_for_sheet(data.english),
        truncate_for_sheet(data.british),
        truncate_for_sheet(data.american),
        truncate_for_sheet(trans.get("Spanish", "")),
        truncate_for_sheet(trans.get("Chinese (Simplified)", "")),
        truncate_for_sheet(trans.get("Hindi", "")),
        truncate_for_sheet(trans.get("Arabic", "")),
        truncate_for_sheet(trans.get("Portuguese", "")),
        truncate_for_sheet(trans.get("French", "")),
        truncate_for_sheet(trans.get("Russian", "")),
        truncate_for_sheet(trans.get("Japanese", "")),
        truncate_for_sheet(trans.get("German", "")),
        truncate_for_sheet(trans.get("Korean", "")),
        data.category,
        data.video_length,
        data.date_transcribed,
        data.detected_language,
        data.docs_link,
        data.status,
        data.voice_name,
        data.voice_directory,
        data.voice_notes,
        data.error,
    ]

    result = (
        _sheets_service()
        .spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=f"'{tab}'!A:A",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        )
        .execute()
    )
    updated = result.get("updates", {}).get("updatedRange", "")
    # e.g. "'Sheet1'!A5:Y5"
    try:
        cell = updated.split("!")[-1].split(":")[0]
        row_num = int("".join(c for c in cell if c.isdigit()))
        return row_num
    except Exception:
        return 0


def read_output_rows() -> list[OutputRow]:
    sheet_url = resolve_output_sheet_url()
    if not sheet_url:
        raise ValueError("Output sheet URL is not configured")

    spreadsheet_id = extract_spreadsheet_id(sheet_url)
    tab = _sheet_tab_name(spreadsheet_id)
    end_col = _col_letter(len(OUTPUT_SHEET_HEADERS) - 1)
    result = (
        _sheets_service()
        .spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"'{tab}'!A:{end_col}")
        .execute()
    )
    values = result.get("values", [])
    if not values:
        return []

    headers = [str(h) for h in values[0]]
    idx = _header_index_map(headers)

    def cell(raw: list, name: str) -> str:
        i = idx.get(name.lower())
        if i is None or i >= len(raw):
            return ""
        return str(raw[i]).strip()

    rows: list[OutputRow] = []
    for i, raw in enumerate(values[1:], start=2):
        name = cell(raw, "Video Name")
        if not name and not cell(raw, "Source Video"):
            continue
        cells = {h: cell(raw, h) for h in OUTPUT_SHEET_HEADERS}
        rows.append(
            OutputRow(
                row_index=i,
                video_name=name,
                source_video=cell(raw, "Source Video"),
                category=cell(raw, "Category"),
                video_length=cell(raw, "Video Length"),
                date_transcribed=cell(raw, "Date Transcribed"),
                docs_link=cell(raw, "Google Docs Link"),
                status=cell(raw, "Status") or BATCH_STATUS_VOICE_READY,
                voice_name=cell(raw, "Voice Name"),
                voice_directory=cell(raw, "Voice Directory"),
                voice_notes=cell(raw, "Voice Notes"),
                error=cell(raw, "Error"),
                cells=cells,
            )
        )
    return rows


def update_output_voice_fields(
    row_index: int,
    *,
    voice_name: str,
    voice_directory: str,
    voice_notes: str,
    status: str = BATCH_STATUS_VOICE_DONE,
) -> None:
    sheet_url = resolve_output_sheet_url()
    if not sheet_url:
        raise ValueError("Output sheet URL is not configured")

    spreadsheet_id = extract_spreadsheet_id(sheet_url)
    tab = _sheet_tab_name(spreadsheet_id)
    end_col = _col_letter(len(OUTPUT_SHEET_HEADERS) - 1)
    header_result = (
        _sheets_service()
        .spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"'{tab}'!A1:{end_col}1")
        .execute()
    )
    headers = [str(h) for h in header_result.get("values", [[]])[0]]
    idx = _header_index_map(headers)

    updates = []
    for col_name, value in [
        ("Status", status),
        ("Voice Name", voice_name),
        ("Voice Directory", voice_directory),
        ("Voice Notes", voice_notes),
    ]:
        col_i = idx.get(col_name.lower())
        if col_i is None:
            continue
        letter = _col_letter(col_i)
        updates.append(
            {"range": f"'{tab}'!{letter}{row_index}", "values": [[value]]}
        )

    if updates:
        _sheets_service().spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "USER_ENTERED", "data": updates},
        ).execute()


def mark_rows_done(row_indexes: list[int]) -> int:
    count = 0
    for ri in row_indexes:
        update_output_voice_fields(
            ri,
            voice_name="",
            voice_directory="",
            voice_notes="Marked done without voice cloning",
            status=BATCH_STATUS_MARKED_DONE,
        )
        count += 1
    return count


def format_duration(seconds: float) -> str:
    s = int(max(0, seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def now_transcribed() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
