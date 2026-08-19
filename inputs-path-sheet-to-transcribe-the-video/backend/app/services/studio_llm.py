"""Shared LLM text completion for studio workflows (OpenAI or Gemini)."""

from __future__ import annotations

import logging

import httpx
from openai import OpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)


class StudioLLMError(Exception):
    pass


def _resolve_provider() -> str:
    settings = get_settings()
    choice = (settings.description_provider or "auto").strip().lower()
    has_openai = bool(settings.openai_api_key.strip())
    has_gemini = bool(settings.gemini_api_key.strip())
    if choice == "openai":
        if not has_openai:
            raise StudioLLMError("OPENAI_API_KEY is not set")
        return "openai"
    if choice == "gemini":
        if not has_gemini:
            raise StudioLLMError("GEMINI_API_KEY is not set")
        return "gemini"
    if has_openai:
        return "openai"
    if has_gemini:
        return "gemini"
    raise StudioLLMError(
        "No LLM configured. Set OPENAI_API_KEY or GEMINI_API_KEY in backend/.env"
    )


def llm_complete(
    system: str,
    user: str,
    *,
    max_tokens: int = 5000,
    temperature: float = 0.65,
) -> str:
    provider = _resolve_provider()
    settings = get_settings()
    if provider == "openai":
        client = OpenAI(api_key=settings.openai_api_key.strip(), timeout=180.0)
        resp = client.chat.completions.create(
            model=settings.openai_model.strip() or "gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = (resp.choices[0].message.content or "").strip()
        if not text:
            raise StudioLLMError("OpenAI returned empty text")
        return text

    model = settings.gemini_model.strip() or "gemini-2.0-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    with httpx.Client(timeout=180.0) as client:
        resp = client.post(url, params={"key": settings.gemini_api_key.strip()}, json=payload)
        if resp.status_code >= 400:
            raise StudioLLMError(f"Gemini error ({resp.status_code}): {resp.text[:400]}")
        data = resp.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        raise StudioLLMError(f"Gemini returned unexpected payload: {data}") from e
    if not text:
        raise StudioLLMError("Gemini returned empty text")
    return text


# Shared constraints — used inside prompts, never shown as a "role picker" in the UI.
CREATOR_BRIEF = """
You write for working YouTube creators who need something they can film THIS week.

Priorities (in order):
1) Retention — open with a concrete payoff promise in the first line; keep open loops; cut fluff.
2) Spoken cadence — write like talk-to-camera, short sentences, natural pauses, no essay tone.
3) Packaging — titles/thumbnails must create curiosity without clickbait lies.
4) Specificity — niche examples, numbers, moments, decisions — never generic advice.
5) Originality — new angle; never copy another channel's script, title formula word-for-word, or distinctive creative expression.
6) YouTube-safe — no scams, guarantees, hate, illegal tips, medical/financial promises, or stolen footage/music advice.

Output rules:
- Markdown only. Use the exact section headers requested.
- Put the ready-to-record spoken script in a fenced code block labeled SCRIPT so creators can copy-paste fast.
- Keep analysis tight; spend most words on the NEW deliverable.
- If something is policy-risky, give a safer rewrite immediately — don't lecture.
""".strip()
