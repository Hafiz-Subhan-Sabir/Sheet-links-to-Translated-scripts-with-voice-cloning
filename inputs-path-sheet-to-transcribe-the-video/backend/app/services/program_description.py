import json
import logging
import time
from pathlib import Path

import httpx
from openai import OpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "program_description.txt"


class DescriptionError(Exception):
    pass


def _load_prompt_template() -> str:
    if _PROMPT_PATH.is_file():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "You are a professional program description writer.\n\n"
        "Write a catalog description from the program title and transcript provided."
    )


def _trim_transcript(transcript: str, max_chars: int) -> str:
    text = transcript.strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    logger.warning("Trimming transcript from %d to %d chars", len(text), max_chars)
    return (
        text[:max_chars]
        + "\n\n[Transcript truncated for API limits — beginning of video retained.]"
    )


def _build_user_input(program_title: str, transcript: str) -> str:
    return (
        f"Course Topic/Link: {program_title.strip()}\n\n"
        f"Table of Contents (video transcript):\n{transcript.strip()}"
    )


def _resolve_provider() -> str:
    settings = get_settings()
    choice = settings.description_provider.strip().lower()
    has_openai = bool(settings.openai_api_key.strip())
    has_gemini = bool(settings.gemini_api_key.strip())

    if choice == "openai":
        if not has_openai:
            raise DescriptionError("DESCRIPTION_PROVIDER=openai but OPENAI_API_KEY is not set")
        return "openai"
    if choice == "gemini":
        if not has_gemini:
            raise DescriptionError("DESCRIPTION_PROVIDER=gemini but GEMINI_API_KEY is not set")
        return "gemini"
    # auto — prefer OpenAI when both are available (typical paid setup)
    if has_openai:
        return "openai"
    if has_gemini:
        return "gemini"
    raise DescriptionError(
        "No description provider configured. Set OPENAI_API_KEY and/or GEMINI_API_KEY in backend .env"
    )


def description_provider_label() -> str:
    """Human-readable provider name for progress messages."""
    try:
        return "OpenAI" if _resolve_provider() == "openai" else "Gemini"
    except DescriptionError:
        return "AI"


def _generate_openai(program_title: str, transcript: str) -> str:
    settings = get_settings()
    api_key = settings.openai_api_key.strip()
    model = settings.openai_model.strip() or "gpt-4o-mini"
    instructions = _load_prompt_template()
    user_input = _build_user_input(program_title, transcript)

    client = OpenAI(api_key=api_key, timeout=300.0)
    last_error: Exception | None = None

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": user_input},
                ],
                temperature=0.7,
                max_tokens=4096,
            )
            text = (response.choices[0].message.content or "").strip()
            if not text:
                raise DescriptionError("OpenAI returned empty text")
            logger.info("Description generated with OpenAI model %s", model)
            return text
        except DescriptionError:
            raise
        except Exception as e:
            err = str(e).lower()
            last_error = e
            if ("429" in err or "rate" in err) and attempt < 2:
                wait = 15 * (attempt + 1)
                logger.warning("OpenAI rate limit — retrying in %ss", wait)
                time.sleep(wait)
                continue
            raise DescriptionError(f"OpenAI description failed: {e}") from e

    raise DescriptionError(f"OpenAI description failed after retries: {last_error}")


def _friendly_gemini_error(status_code: int, body: str, model: str) -> str:
    if status_code != 429:
        return f"Gemini API error ({status_code}): {body[:400]}"
    hint = (
        f"Gemini quota/rate limit hit for model '{model}'. "
        "Enable paid billing on Google AI Studio, or set DESCRIPTION_PROVIDER=openai with OPENAI_API_KEY."
    )
    try:
        data = json.loads(body)
        message = data.get("error", {}).get("message", "")
        if message:
            return f"{hint} — {message[:200]}"
    except json.JSONDecodeError:
        pass
    return hint


def _generate_gemini(program_title: str, transcript: str) -> str:
    settings = get_settings()
    api_key = settings.gemini_api_key.strip()
    instructions = _load_prompt_template()
    user_input = _build_user_input(program_title, transcript)
    prompt = f"{instructions}\n\n---\n\n{user_input}"
    model = settings.gemini_model.strip() or "gemini-2.0-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 4096},
    }

    last_error: Exception | None = None
    data = None
    for attempt in range(3):
        try:
            with httpx.Client(timeout=300.0) as client:
                response = client.post(url, params={"key": api_key}, json=payload)
                if response.status_code == 429 and attempt < 2:
                    wait = 15 * (attempt + 1)
                    logger.warning("Gemini 429 — retrying in %ss", wait)
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                data = response.json()
                break
        except httpx.HTTPStatusError as e:
            detail = e.response.text if e.response is not None else str(e)
            code = e.response.status_code if e.response is not None else 0
            last_error = DescriptionError(_friendly_gemini_error(code, detail, model))
            if code == 429 and attempt < 2:
                time.sleep(15 * (attempt + 1))
                continue
            raise last_error from e
        except Exception as e:
            raise DescriptionError(f"Gemini request failed: {e}") from e
    else:
        if last_error:
            raise last_error
        raise DescriptionError("Gemini request failed after retries")

    candidates = data.get("candidates") or []
    if not candidates:
        raise DescriptionError("Gemini returned no candidates")
    parts = candidates[0].get("content", {}).get("parts") or []
    text_parts = [p.get("text", "") for p in parts if p.get("text")]
    result = "\n".join(text_parts).strip()
    if not result:
        raise DescriptionError("Gemini returned empty text")
    logger.info("Description generated with Gemini model %s", model)
    return result


def generate_program_description(program_title: str, transcript: str) -> str:
    settings = get_settings()
    trimmed = _trim_transcript(transcript, settings.description_transcript_max_chars)
    provider = _resolve_provider()

    if provider == "openai":
        return _generate_openai(program_title, trimmed)
    return _generate_gemini(program_title, trimmed)
