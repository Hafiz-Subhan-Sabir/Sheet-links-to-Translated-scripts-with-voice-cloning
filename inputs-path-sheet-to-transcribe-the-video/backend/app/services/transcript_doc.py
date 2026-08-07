"""Create per-video Google Docs with multilingual transcripts."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.services.google_integrations import create_google_doc_multilingual
from app.services.storage import storage

logger = logging.getLogger(__name__)


def create_transcript_doc(
    *,
    video_name: str,
    source_video: str,
    english: str,
    british: str,
    american: str,
    translations: dict[str, str],
    detected_language: str,
    category: str,
    video_length: str,
) -> tuple[str, str]:
    """
    Create one Google Doc for the video.
    Returns (doc_id, doc_url).
    """
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M UTC")

    # Ordered language sections for the doc
    ordered: dict[str, str] = {
        "English": english,
        "British English": british,
        "American English": american,
    }
    ordered.update(translations)

    notes = f"Category: {category} | Length: {video_length}"
    folder_id = storage.get_admin_config().get("docs_folder_id")

    doc_id, doc_url = create_google_doc_multilingual(
        title=video_name[:200],
        transcript=english,
        translations={k: v for k, v in ordered.items() if k != "English"},
        source_language=detected_language or "en",
        date=date_str,
        time=time_str,
        source_video=source_video,
        notes=notes,
        folder_id=folder_id,
    )
    return doc_id, doc_url
