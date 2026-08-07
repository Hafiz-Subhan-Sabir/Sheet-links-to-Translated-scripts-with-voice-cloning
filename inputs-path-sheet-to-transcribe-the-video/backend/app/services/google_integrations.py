import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from googleapiclient.discovery import build

from app.constants import REGISTRY_HEADERS, REGISTRY_SHEET_NAME
from app.services.auth import get_credentials
from app.services.storage import storage

# Google Docs hard limit is ~1.02M characters; stay below for safety.
GOOGLE_DOC_CHAR_LIMIT = 980_000
INSERT_CHUNK_SIZE = 40_000


def _sanitize_docs_text(text: str) -> str:
    """Remove control characters Google Docs rejects."""
    return re.sub(r"[\x00-\x08\x0c-\x0f\x7f\ue000-\uf8ff]", "", text)


def _append_index(doc: dict) -> int:
    content = doc.get("body", {}).get("content", [])
    if not content:
        return 1
    return content[-1]["endIndex"] - 1


def _batch_insert(docs_service, doc_id: str, index: int, text: str) -> None:
    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{"insertText": {"location": {"index": index}, "text": text}}]},
    ).execute()


def _append_text(docs_service, doc_id: str, text: str) -> int:
    """Append text in chunks; returns total characters written."""
    text = _sanitize_docs_text(text)
    if not text:
        return 0

    written = 0
    offset = 0
    while offset < len(text):
        chunk = text[offset : offset + INSERT_CHUNK_SIZE]
        doc = docs_service.documents().get(documentId=doc_id).execute()
        index = _append_index(doc)
        _batch_insert(docs_service, doc_id, index, chunk)
        written += len(chunk)
        offset += INSERT_CHUNK_SIZE
    return written


def _apply_heading(
    docs_service,
    doc_id: str,
    text: str,
    *,
    style: str = "HEADING_1",
    bold: bool = True,
) -> int:
    """Insert a bold heading paragraph; returns end index after heading."""
    text = _sanitize_docs_text(text.strip())
    if not text:
        return _append_index(docs_service.documents().get(documentId=doc_id).execute())

    doc = docs_service.documents().get(documentId=doc_id).execute()
    start = _append_index(doc)
    end = start + len(text)

    requests: list[dict] = [
        {"insertText": {"location": {"index": start}, "text": f"{text}\n\n"}},
        {
            "updateParagraphStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "paragraphStyle": {"namedStyleType": style},
                "fields": "namedStyleType",
            }
        },
    ]
    if bold:
        requests.append(
            {
                "updateTextStyle": {
                    "range": {"startIndex": start, "endIndex": end},
                    "textStyle": {"bold": True},
                    "fields": "bold",
                }
            }
        )

    docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
    return end + 2


def _apply_title_heading(docs_service, doc_id: str, title: str) -> None:
    _apply_heading(docs_service, doc_id, title, style="HEADING_1", bold=True)


def _move_to_folder(drive_service, doc_id: str, folder_id: Optional[str]) -> None:
    if not folder_id:
        return
    try:
        file_meta = drive_service.files().get(fileId=doc_id, fields="parents").execute()
        prev_parents = ",".join(file_meta.get("parents", []))
        drive_service.files().update(
            fileId=doc_id,
            addParents=folder_id,
            removeParents=prev_parents,
            fields="id, parents",
        ).execute()
    except Exception:
        # Folder move is optional; don't fail the whole pipeline.
        pass


def _insert_page_break(docs_service, doc_id: str) -> None:
    doc = docs_service.documents().get(documentId=doc_id).execute()
    index = _append_index(doc)
    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{"insertPageBreak": {"location": {"index": index}}}]},
    ).execute()


def _append_language_section(
    docs_service,
    doc_id: str,
    lang_name: str,
    text: str,
    *,
    new_page: bool = True,
    heading_style: str = "HEADING_1",
) -> int:
    """Append a bold language heading + transcript on a new page."""
    if new_page:
        _insert_page_break(docs_service, doc_id)
    written = 0
    _apply_heading(docs_service, doc_id, lang_name, style=heading_style, bold=True)
    written += len(lang_name) + 2
    written += _append_text(docs_service, doc_id, text)
    return written


def _create_empty_doc(docs_service, title: str) -> str:
    doc = docs_service.documents().create(body={"title": title[:200]}).execute()
    return doc["documentId"]


def create_google_doc(
    title: str,
    transcript: str,
    date: str,
    time: str,
    source_video: str,
    language: str,
    notes: Optional[str] = None,
    folder_id: Optional[str] = None,
) -> tuple[str, str]:
    creds = get_credentials()
    if not creds:
        raise ValueError("Google account not connected")

    docs_service = build("docs", "v1", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)

    doc_id = _create_empty_doc(docs_service, title)
    _apply_title_heading(docs_service, doc_id, title)

    metadata = (
        f"Date: {date}\n"
        f"Time: {time}\n"
        f"Source: {source_video}\n"
        f"Language: {language}\n"
    )
    if notes:
        metadata += f"Notes: {notes}\n"
    metadata += "\n"

    _append_text(docs_service, doc_id, metadata)
    _apply_heading(docs_service, doc_id, language, style="HEADING_2", bold=True)
    _append_text(docs_service, doc_id, transcript)

    _move_to_folder(drive_service, doc_id, folder_id)
    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    return doc_id, doc_url


def extract_spreadsheet_id(sheet_url: str) -> str:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", sheet_url)
    if match:
        return match.group(1)
    if re.match(r"^[a-zA-Z0-9-_]+$", sheet_url):
        return sheet_url
    raise ValueError("Invalid Google Sheet URL")


def append_to_sheet(
    sheet_url: str,
    title: str,
    doc_url: str,
    date: str,
    time: str,
    source_video: str,
    language: str,
) -> None:
    creds = get_credentials()
    if not creds:
        raise ValueError("Google account not connected")

    spreadsheet_id = extract_spreadsheet_id(sheet_url)
    service = build("sheets", "v4", credentials=creds)
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    row = [title, doc_url, date, time, source_video, language, created_at]
    body = {"values": [row]}

    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range="A:G",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()


def ensure_registry_spreadsheet() -> str:
    """Return saved registry sheet URL, creating 'videos transcripts' if needed."""
    cfg = storage.get_admin_config()
    if cfg.get("sheet_url"):
        return cfg["sheet_url"]

    creds = get_credentials()
    if not creds:
        raise ValueError("Google account not connected")

    service = build("sheets", "v4", credentials=creds)
    spreadsheet = (
        service.spreadsheets()
        .create(
            body={
                "properties": {"title": REGISTRY_SHEET_NAME},
                "sheets": [{"properties": {"title": "Transcripts"}}],
            }
        )
        .execute()
    )

    spreadsheet_id = spreadsheet["spreadsheetId"]
    sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="A1:G1",
        valueInputOption="USER_ENTERED",
        body={"values": [REGISTRY_HEADERS]},
    ).execute()

    storage.save_admin_config(sheet_url)
    return sheet_url


def derive_video_title(
    source: str,
    *,
    preview_title: Optional[str] = None,
    upload_filename: Optional[str] = None,
) -> str:
    if preview_title and preview_title.strip():
        return preview_title.strip()[:200]
    if upload_filename:
        return Path(upload_filename).stem[:200]
    path = Path(source.strip())
    if path.suffix:
        return path.stem[:200] or "Untitled Video"
    return source.strip()[:200] or "Untitled Video"


def create_google_doc_multilingual(
    title: str,
    transcript: str,
    translations: dict[str, str],
    source_language: str,
    date: str,
    time: str,
    source_video: str,
    notes: Optional[str] = None,
    folder_id: Optional[str] = None,
) -> tuple[str, str]:
    """
    Create a single Google Doc with original transcript + all translations.
    Each language gets its own page with a bold heading.
    """
    creds = get_credentials()
    if not creds:
        raise ValueError("Google account not connected")

    docs_service = build("docs", "v1", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)

    doc_id = _create_empty_doc(docs_service, title)
    _apply_title_heading(docs_service, doc_id, title)

    lang_list = [source_language] + list(translations.keys())
    languages_line = ", ".join(lang_list)

    header = (
        f"Date: {date}\n"
        f"Time: {time}\n"
        f"Source: {source_video}\n"
        f"Original language: {source_language}\n"
        f"Languages in this document: {languages_line}\n"
    )
    if notes:
        header += f"Notes: {notes}\n"

    _append_text(docs_service, doc_id, f"{header}\n")
    used = len(header) + 2

    # Original transcript
    _apply_heading(docs_service, doc_id, f"Original — {source_language}", style="HEADING_1", bold=True)
    used += len(source_language) + 20
    used += _append_text(docs_service, doc_id, transcript)

    # All translations in the same document
    for lang_name, text in translations.items():
        remaining = GOOGLE_DOC_CHAR_LIMIT - used
        section_text = text
        if remaining < len(text) + len(lang_name) + 64:
            max_chars = max(0, remaining - 200)
            section_text = (
                text[:max_chars]
                + "\n\n[Section truncated — Google Doc size limit. Original full text is in the app.]"
            )
        used += _append_language_section(
            docs_service,
            doc_id,
            lang_name,
            section_text,
            new_page=True,
            heading_style="HEADING_1",
        )

    _move_to_folder(drive_service, doc_id, folder_id)
    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    return doc_id, doc_url
