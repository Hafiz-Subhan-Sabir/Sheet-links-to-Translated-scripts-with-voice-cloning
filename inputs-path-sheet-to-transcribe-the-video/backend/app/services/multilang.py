"""Translate transcript into English + top languages in parallel."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from app.config import get_settings
from app.constants import TRANSLATION_LANGUAGES
from app.services.translate import translate_text

logger = logging.getLogger(__name__)


def ensure_english(transcript: str, detected_language: Optional[str]) -> str:
    """Return English text — translate if source is not English."""
    lang = (detected_language or "").lower().split("-")[0]
    if not lang or lang in ("en", "eng", "english"):
        return transcript
    try:
        text, _ = translate_text(transcript, "en", source_language=detected_language)
        return text
    except Exception as e:
        logger.warning(
            "Could not translate to English (%s): %s — using original",
            detected_language,
            e,
        )
        return transcript


def translate_all_languages(
    english: str,
    *,
    on_progress: Optional[Callable[[str, float], None]] = None,
) -> dict[str, str]:
    """
    Translate English transcript into the top 10 languages.
    Returns {display_name: translated_text}.
    """
    settings = get_settings()
    workers = max(1, min(settings.translate_workers, len(TRANSLATION_LANGUAGES)))
    results: dict[str, str] = {}
    total = len(TRANSLATION_LANGUAGES)
    done = 0

    def _one(code: str, name: str) -> tuple[str, str]:
        text, _ = translate_text(english, code, source_language="en")
        return name, text

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_one, code, name): name for code, name in TRANSLATION_LANGUAGES
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                lang_name, text = future.result()
                results[lang_name] = text
            except Exception as e:
                logger.warning("Translation to %s failed: %s", name, e)
                results[name] = f"[Translation failed: {e}]"
            done += 1
            if on_progress:
                on_progress(f"Translated {done}/{total}", done / total)

    return {name: results.get(name, "") for _, name in TRANSLATION_LANGUAGES}
