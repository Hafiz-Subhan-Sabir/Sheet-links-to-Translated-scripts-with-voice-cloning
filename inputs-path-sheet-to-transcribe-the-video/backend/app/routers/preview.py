import time

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.models.schemas import PrefetchRequest, PrefetchStatusResponse
from app.services.prefetch import prefetch_manager, schedule_prefetch
from app.services.preview import get_video_preview
from app.services.video import VideoError

router = APIRouter(prefix="/api", tags=["preview"])


class VideoPreviewRequest(PrefetchRequest):
    pass


@router.post("/video/preview")
def video_preview(body: VideoPreviewRequest):
    try:
        return get_video_preview(body.url)
    except VideoError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/video/prefetch", response_model=PrefetchStatusResponse)
def video_prefetch(body: PrefetchRequest):
    settings = get_settings()
    if not settings.prefetch_enabled:
        raise HTTPException(status_code=503, detail="Prefetch is disabled")
    try:
        entry = schedule_prefetch(body.url)
        return PrefetchStatusResponse(**prefetch_manager.to_dict(entry))
    except VideoError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/video/prefetch/{cache_id}", response_model=PrefetchStatusResponse)
def video_prefetch_status(cache_id: str):
    entry = prefetch_manager.get(cache_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Prefetch not found")
    return PrefetchStatusResponse(**prefetch_manager.to_dict(entry))
