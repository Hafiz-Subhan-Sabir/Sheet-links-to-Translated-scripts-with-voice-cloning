from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal, Optional

import httpx

from app.config import get_settings

TranslateProvider = Literal["google_api", "google_free"]

MAX_CHUNK = 4500


def translate_text(
    text: str,
    target_language: str,
    source_language: Optional[str] = None,
) -> tuple[str, TranslateProvider]:
    settings = get_settings()
    mode = settings.google_translate_mode.lower()
    has_api_key = bool(settings.google_translate_api_key.strip())

    if mode == "api" or (mode == "auto" and has_api_key):
        if not has_api_key:
            raise ValueError(
                "GOOGLE_TRANSLATE_API_KEY is required when GOOGLE_TRANSLATE_MODE=api"
            )
        return (
            _translate_google_cloud_api(
                text, target_language, source_language, settings.google_translate_api_key.strip()
            ),
            "google_api",
        )

    return (
        _translate_google_free(text, target_language, source_language),
        "google_free",
    )


def _normalize_lang(code: Optional[str]) -> Optional[str]:
    if not code or code == "auto" or code == "none":
        return None
    return code


def _translate_parts_parallel(
    parts: list[str],
    translate_part,
) -> str:
    if len(parts) <= 1:
        return translate_part(parts[0]) if parts else ""

    settings = get_settings()
    workers = max(1, min(settings.translate_workers, len(parts)))
    results: list[str | None] = [None] * len(parts)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(translate_part, part): i for i, part in enumerate(parts)}
        for future in as_completed(futures):
            idx = futures[future]
            results[idx] = future.result()

    return "\n".join(r for r in results if r)


def _chunk_text(text: str, max_len: int = MAX_CHUNK) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_len, len(text))
        if end < len(text):
            split_at = text.rfind("\n", start, end)
            if split_at > start + max_len // 2:
                end = split_at + 1
        chunks.append(text[start:end])
        start = end
    return chunks


def _translate_google_cloud_api(
    text: str,
    target: str,
    source: Optional[str],
    api_key: str,
) -> str:
    """Official Google Cloud Translation API v2 (requires API key)."""
    url = "https://translation.googleapis.com/language/translate/v2"
    src = _normalize_lang(source)
    parts = _chunk_text(text)

    with httpx.Client(timeout=120.0) as client:
        def _one(part: str) -> str:
            params: dict = {
                "key": api_key,
                "q": part,
                "target": target,
                "format": "text",
            }
            if src:
                params["source"] = src
            resp = client.post(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data["data"]["translations"][0]["translatedText"]

        return _translate_parts_parallel(parts, _one)


def _translate_google_free(
    text: str,
    target: str,
    source: Optional[str],
) -> str:
    """
    Free Google Translate (no API key) — same idea as npm `google-translator`.
    Uses deep-translator against Google Translate web; auto-detect when source is omitted.
    """
    from deep_translator import GoogleTranslator

    src = _normalize_lang(source)
    translator = GoogleTranslator(source=src or "auto", target=target)
    parts = _chunk_text(text)
    return _translate_parts_parallel(parts, translator.translate)
