import logging
import threading
from typing import Optional

from googleapiclient.discovery import build

from app.config import get_settings
from app.constants import OUTPUT_DOC_TITLE
from app.services.auth import get_credentials
from app.services.google_integrations import (
    _append_index,
    _append_text,
    _apply_heading,
    _create_empty_doc,
    _insert_page_break,
    _move_to_folder,
)
from app.services.storage import storage

logger = logging.getLogger(__name__)

_doc_append_lock = threading.Lock()


def _output_doc_title() -> str:
    title = get_settings().output_doc_title.strip()
    return title or OUTPUT_DOC_TITLE


def _build_services():
    creds = get_credentials()
    if not creds:
        raise ValueError("Google account not connected")
    docs_service = build("docs", "v1", credentials=creds, cache_discovery=False)
    drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
    return docs_service, drive_service


def _find_doc_by_title(drive_service, title: str) -> Optional[str]:
    escaped = title.replace("'", "\\'")
    query = (
        f"name = '{escaped}' "
        "and mimeType = 'application/vnd.google-apps.document' "
        "and trashed = false"
    )
    result = (
        drive_service.files()
        .list(q=query, spaces="drive", fields="files(id, name)", pageSize=5)
        .execute()
    )
    files = result.get("files", [])
    if not files:
        return None
    return files[0]["id"]


def _doc_has_content(docs_service, doc_id: str) -> bool:
    doc = docs_service.documents().get(documentId=doc_id, fields="body.content").execute()
    content = doc.get("body", {}).get("content", [])
    if len(content) > 1:
        return True
    if not content:
        return False
    paragraph = content[0].get("paragraph", {})
    elements = paragraph.get("elements", [])
    for el in elements:
        text = el.get("textRun", {}).get("content", "")
        if text.strip():
            return True
    return False


def get_output_doc_url() -> Optional[str]:
    cfg = storage.get_admin_config()
    doc_id = cfg.get("output_doc_id")
    if doc_id:
        return f"https://docs.google.com/document/d/{doc_id}/edit"
    return None


def find_or_create_output_doc() -> tuple[str, str]:
    """Return (doc_id, doc_url) for the shared output Google Doc."""
    cfg = storage.get_admin_config()
    cached_id = cfg.get("output_doc_id")
    title = _output_doc_title()
    docs_service, drive_service = _build_services()

    if cached_id:
        try:
            docs_service.documents().get(documentId=cached_id, fields="documentId,title").execute()
            return cached_id, f"https://docs.google.com/document/d/{cached_id}/edit"
        except Exception:
            logger.warning("Cached output doc %s not accessible — searching Drive", cached_id)

    doc_id = _find_doc_by_title(drive_service, title)
    if not doc_id:
        doc_id = _create_empty_doc(docs_service, title)
        folder_id = cfg.get("docs_folder_id")
        _move_to_folder(drive_service, doc_id, folder_id)

    storage.save_output_doc_id(doc_id)
    return doc_id, f"https://docs.google.com/document/d/{doc_id}/edit"


def append_program_section(program_title: str, description: str) -> str:
    """Append one program section to the shared output doc. Returns doc URL."""
    with _doc_append_lock:
        doc_id, doc_url = find_or_create_output_doc()
        docs_service, _ = _build_services()

        if _doc_has_content(docs_service, doc_id):
            _insert_page_break(docs_service, doc_id)

        _apply_heading(docs_service, doc_id, program_title, style="HEADING_1", bold=True)
        _append_text(docs_service, doc_id, f"{description.strip()}\n\n")
        return doc_url
