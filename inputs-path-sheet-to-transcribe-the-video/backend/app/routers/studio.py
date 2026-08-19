"""Studio API — original content, viral compare, Shorts blueprints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.studio import (
    analyze_shorts_blueprint,
    analyze_viral_and_suggest,
    generate_original_content,
)
from app.services.studio_llm import StudioLLMError

router = APIRouter(prefix="/api/studio", tags=["studio"])


class OriginalRequest(BaseModel):
    topic: str
    niche: str = ""
    audience: str = ""
    format_hint: str = "long-form YouTube video"
    length_minutes: int = Field(default=8, ge=1, le=60)


class UrlsRequest(BaseModel):
    urls: list[str]
    niche: str = ""
    goal: str = ""


@router.post("/original")
def studio_original(body: OriginalRequest):
    try:
        return generate_original_content(
            topic=body.topic,
            niche=body.niche,
            audience=body.audience,
            format_hint=body.format_hint,
            length_minutes=body.length_minutes,
        )
    except (ValueError, StudioLLMError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/viral")
def studio_viral(body: UrlsRequest):
    try:
        return analyze_viral_and_suggest(urls=body.urls, niche=body.niche, goal=body.goal)
    except (ValueError, StudioLLMError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/shorts")
def studio_shorts(body: UrlsRequest):
    try:
        return analyze_shorts_blueprint(urls=body.urls, niche=body.niche, goal=body.goal or "high engagement Shorts")
    except (ValueError, StudioLLMError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
