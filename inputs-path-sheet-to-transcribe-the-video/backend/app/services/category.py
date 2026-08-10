"""Classify video category from title + transcript snippet using OpenAI/Gemini."""

from __future__ import annotations

import logging

import httpx
from openai import OpenAI

from app.config import get_settings
from app.constants import VIDEO_CATEGORIES

logger = logging.getLogger(__name__)


def _resolve_provider() -> str | None:
    settings = get_settings()
    choice = settings.description_provider.strip().lower()
    # off/none/local = skip LLM (use keyword fallback only)
    if choice in {"off", "none", "false", "0", "local"}:
        return None
    has_openai = bool(settings.openai_api_key.strip())
    has_gemini = bool(settings.gemini_api_key.strip())
    if choice == "openai" and has_openai:
        return "openai"
    if choice == "gemini" and has_gemini:
        return "gemini"
    if choice == "auto":
        if has_openai:
            return "openai"
        if has_gemini:
            return "gemini"
        return None
    if has_openai:
        return "openai"
    if has_gemini:
        return "gemini"
    return None


def _normalize_category(raw: str) -> str:
    text = raw.strip().strip('"').strip("'")
    lower = text.lower()
    for cat in VIDEO_CATEGORIES:
        if cat.lower() == lower or cat.lower() in lower:
            return cat
    # fuzzy keyword map
    keywords = {
        "Tech": ["tech", "software", "coding", "ai", "computer", "gadget"],
        "Finance": ["finance", "invest", "stock", "crypto", "money", "trading"],
        "Entertainment": ["entertain", "movie", "film", "celebrity", "show"],
        "Songs / Music": ["song", "music", "lyrics", "album", "singer", "rap"],
        "Education": ["educat", "tutorial", "learn", "course", "lesson"],
        "News": ["news", "headline", "breaking", "politics"],
        "Gaming": ["game", "gaming", "esport", "gameplay"],
        "Lifestyle": ["lifestyle", "vlog", "travel", "fashion"],
        "Sports": ["sport", "football", "cricket", "nba", "soccer"],
        "Health": ["health", "fitness", "medical", "workout"],
        "Business": ["business", "startup", "entrepreneur", "marketing"],
        "Comedy": ["comedy", "funny", "stand-up", "humor", "humour"],
    }
    for cat, keys in keywords.items():
        if any(k in lower for k in keys):
            return cat
    return "Other"


def classify_category(video_name: str, transcript: str) -> str:
    snippet = transcript[:4000]
    provider = _resolve_provider()
    if not provider:
        return _normalize_category(f"{video_name} {snippet[:500]}")

    cats = ", ".join(VIDEO_CATEGORIES)
    prompt = (
        f"Classify this video into exactly one category from this list:\n{cats}\n\n"
        f"Video title: {video_name}\n\n"
        f"Transcript excerpt:\n{snippet}\n\n"
        "Reply with only the category name, nothing else."
    )

    try:
        if provider == "openai":
            settings = get_settings()
            client = OpenAI(api_key=settings.openai_api_key.strip())
            resp = client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=20,
            )
            raw = (resp.choices[0].message.content or "").strip()
            return _normalize_category(raw)

        settings = get_settings()
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.gemini_model}:generateContent"
        )
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                url,
                params={"key": settings.gemini_api_key.strip()},
                json={"contents": [{"parts": [{"text": prompt}]}]},
            )
            r.raise_for_status()
            data = r.json()
            raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            return _normalize_category(raw)
    except Exception as e:
        logger.warning("Category classification failed: %s", e)
        return _normalize_category(f"{video_name} {snippet[:500]}")
