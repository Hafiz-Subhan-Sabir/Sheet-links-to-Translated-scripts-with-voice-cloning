"""Prospect problem finder API."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.prospect import analyze_prospect
from app.services.studio_llm import StudioLLMError

router = APIRouter(prefix="/api/prospect", tags=["prospect"])


class ProspectAnalyzeRequest(BaseModel):
    video_url: str = ""
    website_url: str = ""
    google_maps_url: str = ""
    app_url: str = ""
    business_description: str = ""
    your_offer: str = ""


@router.post("/analyze")
def prospect_analyze(body: ProspectAnalyzeRequest):
    try:
        return analyze_prospect(
            video_url=body.video_url,
            website_url=body.website_url,
            google_maps_url=body.google_maps_url,
            app_url=body.app_url,
            business_description=body.business_description,
            your_offer=body.your_offer,
        )
    except (ValueError, StudioLLMError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
