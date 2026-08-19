"""Studio workflows: original scripts, viral compare, shorts blueprints."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from app.services.media_bins import ensure_yt_dlp
from app.services.studio_llm import CREATOR_BRIEF, llm_complete

logger = logging.getLogger(__name__)


def _fetch_video_meta(url: str) -> dict[str, Any]:
    ensure_yt_dlp()
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise ValueError(f"Could not read metadata for {url}")
    desc = (info.get("description") or "")[:900]
    tags = info.get("tags") or []
    if isinstance(tags, list):
        tags = [str(t) for t in tags[:20]]
    else:
        tags = []
    views = int(info.get("view_count") or 0)
    likes = info.get("like_count")
    like_count = int(likes) if likes is not None else None
    duration = float(info.get("duration") or 0)
    upload_date = info.get("upload_date") or ""
    days_live = None
    if len(upload_date) == 8:
        try:
            uploaded = datetime.strptime(upload_date, "%Y%m%d")
            days_live = max(1, (datetime.utcnow() - uploaded).days)
        except Exception:
            days_live = None
    views_per_day = round(views / days_live, 1) if days_live else None
    eng = round((like_count / views) * 100, 3) if like_count and views else None
    return {
        "url": url,
        "id": info.get("id") or "",
        "title": info.get("title") or "",
        "channel": info.get("uploader") or info.get("channel") or "",
        "view_count": views,
        "like_count": like_count,
        "duration": duration,
        "upload_date": upload_date,
        "days_live": days_live,
        "views_per_day": views_per_day,
        "like_rate_pct": eng,
        "description_snip": desc,
        "tags": tags,
        "is_short": bool(
            duration <= 60
            or "shorts" in (url or "").lower()
            or (info.get("width") or 0) < (info.get("height") or 0)
        ),
    }


def gather_metas(urls: list[str], *, limit: int = 10) -> list[dict[str, Any]]:
    cleaned: list[str] = []
    for u in urls:
        u = (u or "").strip()
        if u and u not in cleaned:
            cleaned.append(u)
    cleaned = cleaned[:limit]
    if len(cleaned) < 3:
        raise ValueError("Paste at least 3 video URLs (up to 10).")

    metas: list[dict[str, Any]] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=min(6, len(cleaned))) as pool:
        futures = {pool.submit(_fetch_video_meta, url): url for url in cleaned}
        for fut in as_completed(futures):
            url = futures[fut]
            try:
                metas.append(fut.result())
            except Exception as e:
                logger.warning("Meta fetch failed for %s: %s", url, e)
                errors.append(f"{url}: {e}")

    if len(metas) < 3:
        raise ValueError(
            "Need metadata for at least 3 videos. "
            + ("; ".join(errors[:3]) if errors else "Check the links.")
        )
    metas.sort(key=lambda m: (m.get("views_per_day") or 0, m.get("view_count") or 0), reverse=True)
    return metas


def _format_metas(metas: list[dict[str, Any]]) -> str:
    lines = []
    for i, m in enumerate(metas, 1):
        lines.append(
            f"{i}. title={m['title']!r} | channel={m['channel']!r} | views={m['view_count']} | "
            f"views/day={m.get('views_per_day')} | like%={m.get('like_rate_pct')} | "
            f"duration={m['duration']:.0f}s | short={m['is_short']} | uploaded={m.get('upload_date')} | "
            f"tags={', '.join(m['tags'][:8])} | desc={m['description_snip'][:280]!r} | url={m['url']}"
        )
    return "\n".join(lines)


def generate_original_content(
    *,
    topic: str,
    niche: str = "",
    audience: str = "",
    format_hint: str = "long-form YouTube video",
    length_minutes: int = 8,
) -> dict[str, Any]:
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("What is the video about?")
    is_short = "short" in (format_hint or "").lower()
    target = "35-55 seconds" if is_short else f"~{length_minutes} minutes"
    system = f"""{CREATOR_BRIEF}

Build a complete ORIGINAL video package from a creator idea.
Infer niche/audience from the topic when not given.
Sections (exact headers):
## Titles (3)
## Thumbnail text (3 short options)
## Promise (one sentence)
## Hook (first 8 seconds — spoken)
## Beat sheet
## SCRIPT
(fenced code block with the full spoken script only)
## End screen / CTA
## Film notes (B-roll, cuts, pacing — 5 bullets max)
## Policy quick-check (1-3 bullets)
"""
    user = (
        f"Idea: {topic}\n"
        f"Format: {format_hint} ({target})\n"
        f"Niche hint: {niche or 'infer'}\n"
        f"Audience hint: {audience or 'infer'}\n"
        "Write the SCRIPT ready to record aloud. No filler intros."
    )
    markdown = llm_complete(system, user, max_tokens=5500, temperature=0.75)
    return {"mode": "original", "topic": topic, "niche": niche, "markdown": markdown}


def analyze_viral_and_suggest(
    *,
    urls: list[str],
    niche: str = "",
    goal: str = "",
) -> dict[str, Any]:
    metas = gather_metas(urls, limit=10)
    system = f"""{CREATOR_BRIEF}

Competitive pattern analysis → ONE new video the creator can publish.
Use metadata only (titles, views, velocity, tags, descriptions). Never recreate their scripts.

Think like a creator reverse-engineering retention:
- What promise do top titles make?
- What curiosity gap / conflict / transformation shows up?
- What is overdone vs underserved in this set?
- Which top video has the best velocity (views/day), not just raw views?

Then invent a NEW concept that can win the same search/browse intent without cloning anyone.

Sections (exact headers):
## What's working (patterns from the set)
## Gaps (what they skip)
## Winning concept (your original idea in 3 sentences)
## Titles (3)
## Thumbnail text (3)
## Hook / Body / Payoff (blueprint)
## SCRIPT
(fenced code block — full spoken script for the NEW video, ~7-10 min conversational unless Shorts-length fits better)
## Why this can beat them (differentiation)
## Policy quick-check
"""
    user = (
        f"Niche hint: {niche or 'infer from the set'}\n"
        f"Creator goal: {goal or 'views + retention + subscribe CTA'}\n"
        f"Videos sorted by velocity then views:\n{_format_metas(metas)}\n"
        "Prioritize the #1 concept with a complete SCRIPT."
    )
    markdown = llm_complete(system, user, max_tokens=6000, temperature=0.55)
    return {"mode": "viral", "videos": metas, "markdown": markdown}


def analyze_shorts_blueprint(
    *,
    urls: list[str],
    niche: str = "",
    goal: str = "high retention Shorts",
) -> dict[str, Any]:
    metas = gather_metas(urls, limit=10)
    system = f"""{CREATOR_BRIEF}

Shorts / vertical / ads-style engagement specialist.
Analyze viral patterns from metadata only. Write ORIGINAL spoken lines — never quote hooks verbatim from the refs.

Shorts craft rules:
- Hook in first 1-2 seconds (visual + spoken).
- One idea only. Cut every polite intro.
- Pattern interrupt mid-short.
- Loopable ending or hard CTA.
- On-screen text must be readable in 1 glance.

Sections (exact headers):
## Patterns that travel (from the set)
## Winning Shorts concept
## Titles / first-line text (3)
## Hook (0-2s) spoken + on-screen
## Body beats (spoken)
## Ending / loop / CTA
## SCRIPT
(fenced code block — full 30-55s spoken script)
## On-screen text timeline
## 3 alternate hooks (A/B)
## Sound vibe (describe mood only — no copyrighted track names)
## Policy quick-check
"""
    user = (
        f"Niche hint: {niche or 'infer'}\n"
        f"Goal: {goal or 'high retention Shorts'}\n"
        f"Reference videos:\n{_format_metas(metas)}\n"
        "Deliver a film-ready SCRIPT first; keep analysis short."
    )
    markdown = llm_complete(system, user, max_tokens=5200, temperature=0.6)
    return {"mode": "shorts", "videos": metas, "markdown": markdown}
