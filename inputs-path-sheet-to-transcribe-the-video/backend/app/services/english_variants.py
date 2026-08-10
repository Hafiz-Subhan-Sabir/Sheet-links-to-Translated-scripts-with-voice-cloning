"""Produce British and American English variants of a transcript."""

from __future__ import annotations

import logging
import re

import httpx
from openai import OpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

# Common American → British spelling swaps (and reverse)
_AM_TO_BR = [
    (r"\bcolor\b", "colour"),
    (r"\bcolors\b", "colours"),
    (r"\bfavor\b", "favour"),
    (r"\bfavorite\b", "favourite"),
    (r"\bhonor\b", "honour"),
    (r"\bbehavior\b", "behaviour"),
    (r"\bcenter\b", "centre"),
    (r"\bcenters\b", "centres"),
    (r"\btheater\b", "theatre"),
    (r"\borganize\b", "organise"),
    (r"\borganized\b", "organised"),
    (r"\brealize\b", "realise"),
    (r"\brealized\b", "realised"),
    (r"\banalyze\b", "analyse"),
    (r"\bdefense\b", "defence"),
    (r"\blicense\b", "licence"),
    (r"\btraveling\b", "travelling"),
    (r"\bcanceled\b", "cancelled"),
    (r"\bprogram\b", "programme"),
    (r"\bprograms\b", "programmes"),
]

_BR_TO_AM = [
    (r"\bcolour\b", "color"),
    (r"\bcolours\b", "colors"),
    (r"\bfavour\b", "favor"),
    (r"\bfavourite\b", "favorite"),
    (r"\bhonour\b", "honor"),
    (r"\bbehaviour\b", "behavior"),
    (r"\bcentre\b", "center"),
    (r"\bcentres\b", "centers"),
    (r"\btheatre\b", "theater"),
    (r"\borganise\b", "organize"),
    (r"\borganised\b", "organized"),
    (r"\brealise\b", "realize"),
    (r"\brealised\b", "realized"),
    (r"\banalyse\b", "analyze"),
    (r"\bdefence\b", "defense"),
    (r"\blicence\b", "license"),
    (r"\btravelling\b", "traveling"),
    (r"\bcancelled\b", "canceled"),
    (r"\bprogramme\b", "program"),
    (r"\bprogrammes\b", "programs"),
]


def _apply_swaps(text: str, pairs: list[tuple[str, str]]) -> str:
    out = text
    for pattern, repl in pairs:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    return out


def _llm_variant(text: str, style: str) -> str | None:
    settings = get_settings()
    choice = settings.description_provider.strip().lower()
    if choice in {"off", "none", "false", "0", "local"}:
        return None

    has_openai = bool(settings.openai_api_key.strip())
    has_gemini = bool(settings.gemini_api_key.strip())
    if not has_openai and not has_gemini:
        return None

    # Keep LLM calls bounded for long transcripts
    max_chars = 12_000
    truncated = text if len(text) <= max_chars else text[:max_chars] + "\n\n[…]"
    prompt = (
        f"Rewrite the following transcript into {style} English. "
        "Preserve meaning, timestamps, and paragraph structure. "
        "Only change spelling, vocabulary, and phrasing to match the target variant. "
        "Output only the rewritten transcript.\n\n"
        f"{truncated}"
    )

    try:
        if has_openai:
            client = OpenAI(api_key=settings.openai_api_key.strip())
            resp = client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            return (resp.choices[0].message.content or "").strip() or None

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.gemini_model}:generateContent"
        )
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                url,
                params={"key": settings.gemini_api_key.strip()},
                json={"contents": [{"parts": [{"text": prompt}]}]},
            )
            r.raise_for_status()
            data = r.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip() or None
    except Exception as e:
        logger.warning("English variant LLM failed (%s): %s", style, e)
        return None


def make_british(english: str) -> str:
    llm = _llm_variant(english, "British")
    if llm:
        return llm
    return _apply_swaps(english, _AM_TO_BR)


def make_american(english: str) -> str:
    llm = _llm_variant(english, "American")
    if llm:
        return llm
    return _apply_swaps(english, _BR_TO_AM)
