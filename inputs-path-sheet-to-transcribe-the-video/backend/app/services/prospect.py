"""Prospect problem finder — diagnose business pain from URLs or description."""

from __future__ import annotations

import logging
import re
from typing import Any
import httpx

from app.services.studio import _fetch_video_meta
from app.services.studio_llm import llm_complete

logger = logging.getLogger(__name__)

PROSPECT_SYSTEM = """
You are an expert business analyst and automation consultant who finds the REAL problems behind any business — not surface symptoms.

Your job:
1) Infer what the business does, who they serve, and how they likely operate today
2) Identify their #1 operational bottleneck (the thing costing them time, money, or customers)
3) List 3–5 specific pain points — especially where automation, AI, or software would help
4) Rank problems by urgency and revenue impact
5) Suggest how to open a pitch conversation (problem-first, not product-first)

You may receive: video metadata, website snippets, Google Maps info, app store info, or a plain business description.
When data is thin, state assumptions clearly and still give actionable hypotheses.

Output rules — Markdown only, use these sections:

## Business snapshot
(What they do, who they serve, likely size/stage — 3–5 bullets)

## Biggest problem (lead with this in your pitch)
(One paragraph — the #1 pain you'd lead with on a call)

## Pain points ranked
(Numbered list — each with: problem → why it hurts → automation/AI angle)

## What they're probably doing manually today
(Bullet list of workflows ripe for automation)

## Pitch opener (problem-first)
(2–3 sentences you'd say on a cold call or DM — no product name unless provided)

## Discovery questions
(5 questions to validate the problem on a live call)

## Recommended automation stack (high level)
(Bullet list — e.g. CRM, booking bot, review automation — keep practical)

## Confidence & gaps
(What you're sure about vs what you'd verify on a call)

Be specific to THIS business — never generic "you need a website" advice unless that's truly the gap.
""".strip()

_STRIP_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _clean_html(html: str, *, limit: int = 4000) -> str:
    text = _STRIP_TAGS.sub(" ", html)
    text = _WS.sub(" ", text).strip()
    return text[:limit]


def _fetch_page_snippet(url: str, *, limit: int = 4000) -> dict[str, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; VoltScriptProspect/1.0; +https://localhost)"
        ),
        "Accept": "text/html,application/xhtml+xml",
    }
    with httpx.Client(timeout=25.0, follow_redirects=True, headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()
        html = resp.text

    title = ""
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    if m:
        title = _WS.sub(" ", m.group(1)).strip()

    desc = ""
    for pat in (
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description',
    ):
        dm = re.search(pat, html, re.I)
        if dm:
            desc = _WS.sub(" ", dm.group(1)).strip()
            break

    body = _clean_html(html, limit=limit)
    return {"url": url, "title": title, "description": desc, "body_snippet": body}


def _classify_url(url: str) -> str:
    lower = url.lower()
    if "google.com/maps" in lower or "maps.app.goo.gl" in lower or "goo.gl/maps" in lower:
        return "google_maps"
    if any(x in lower for x in ("apps.apple.com", "play.google.com", "appstore.com")):
        return "app_store"
    if any(
        x in lower
        for x in (
            "youtube.com",
            "youtu.be",
            "tiktok.com",
            "instagram.com",
            "facebook.com",
            "vimeo.com",
        )
    ):
        return "video"
    return "website"


def _gather_context(
    *,
    video_url: str = "",
    website_url: str = "",
    google_maps_url: str = "",
    app_url: str = "",
    business_description: str = "",
) -> dict[str, Any]:
    sources: list[dict[str, Any]] = []
    errors: list[str] = []

    url_jobs: list[tuple[str, str]] = []
    if video_url.strip():
        url_jobs.append(("video", video_url.strip()))
    if website_url.strip():
        url_jobs.append(("website", website_url.strip()))
    if google_maps_url.strip():
        url_jobs.append(("google_maps", google_maps_url.strip()))
    if app_url.strip():
        url_jobs.append(("app", app_url.strip()))

    for kind, url in url_jobs:
        try:
            if kind == "video":
                meta = _fetch_video_meta(url)
                sources.append({"type": "video", "data": meta})
            else:
                snippet = _fetch_page_snippet(url)
                snippet["detected_type"] = _classify_url(url)
                sources.append({"type": kind, "data": snippet})
        except Exception as e:
            logger.warning("Prospect fetch failed for %s: %s", url, e)
            errors.append(f"{url}: {e}")

    if not sources and not business_description.strip():
        raise ValueError(
            "Add at least one URL (video, website, Google Maps, or app) "
            "OR describe the business in your own words."
        )

    return {
        "sources": sources,
        "business_description": business_description.strip(),
        "errors": errors,
    }


def _format_context(ctx: dict[str, Any]) -> str:
    lines: list[str] = []
    if ctx.get("business_description"):
        lines.append(f"User-provided business description:\n{ctx['business_description']}\n")

    for src in ctx.get("sources") or []:
        stype = src.get("type")
        data = src.get("data") or {}
        if stype == "video":
            lines.append(
                f"VIDEO ({data.get('url')}):\n"
                f"  title={data.get('title')!r}\n"
                f"  channel={data.get('channel')!r}\n"
                f"  views={data.get('view_count')}\n"
                f"  duration={data.get('duration')}s\n"
                f"  tags={', '.join(data.get('tags') or [])}\n"
                f"  description={data.get('description_snip', '')[:600]!r}\n"
            )
        else:
            lines.append(
                f"{stype.upper()} ({data.get('url')}):\n"
                f"  title={data.get('title')!r}\n"
                f"  description={data.get('description')!r}\n"
                f"  snippet={data.get('body_snippet', '')[:800]!r}\n"
            )

    if ctx.get("errors"):
        lines.append("Fetch warnings:\n" + "\n".join(f"- {e}" for e in ctx["errors"]))

    return "\n".join(lines)


def analyze_prospect(
    *,
    video_url: str = "",
    website_url: str = "",
    google_maps_url: str = "",
    app_url: str = "",
    business_description: str = "",
    your_offer: str = "",
) -> dict[str, Any]:
    ctx = _gather_context(
        video_url=video_url,
        website_url=website_url,
        google_maps_url=google_maps_url,
        app_url=app_url,
        business_description=business_description,
    )

    offer_block = ""
    if your_offer.strip():
        offer_block = f"\n\nWhat WE sell (tailor the pitch to fit this):\n{your_offer.strip()}"

    user_prompt = f"""
Research inputs:
{_format_context(ctx)}
{offer_block}

Find this business's biggest problems and how to pitch automation/services problem-first.
""".strip()

    markdown = llm_complete(PROSPECT_SYSTEM, user_prompt, max_tokens=4500, temperature=0.5)
    return {
        "mode": "prospect_analysis",
        "sources_used": len(ctx.get("sources") or []),
        "fetch_warnings": ctx.get("errors") or [],
        "markdown": markdown,
    }
