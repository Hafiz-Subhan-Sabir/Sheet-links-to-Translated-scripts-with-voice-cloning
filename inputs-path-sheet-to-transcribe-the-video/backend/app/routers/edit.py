"""Auto visual plan + rough cut + CapCut edit pack."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.models.schemas import JobStatusResponse
from app.services.jobs import job_manager
from app.services.visual_edit import VisualEditError, edit_packs_dir, run_auto_edit_pack
from app.services.workers import submit_task

router = APIRouter(prefix="/api/edit", tags=["edit"])


class AutoEditRequest(BaseModel):
    script: str
    title: str = "edit"
    voice_mp3_filename: Optional[str] = None
    generate_images: bool = True
    build_video: bool = True


class AutoEditResponse(BaseModel):
    job_id: str


@router.post("/auto-pack", response_model=AutoEditResponse)
def start_auto_edit_pack(body: AutoEditRequest):
    script = (body.script or "").strip()
    if len(script) < 20:
        raise HTTPException(status_code=400, detail="Paste a longer script first")
    job_id = job_manager.create()
    submit_task(
        _run_auto_edit_job,
        job_id,
        script,
        (body.title or "edit").strip() or "edit",
        body.voice_mp3_filename,
        bool(body.generate_images),
        bool(body.build_video),
    )
    return AutoEditResponse(job_id=job_id)


@router.get("/status/{job_id}", response_model=JobStatusResponse)
def edit_job_status(job_id: str):
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(**job_manager.to_response(job_id))


@router.get("/download/{filename}")
def download_edit_file(filename: str, inline: bool = False):
    safe = Path(filename).name
    if safe != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    allowed = {".zip", ".mp4", ".jpg", ".jpeg", ".png", ".srt", ".json", ".md", ".mp3"}
    if Path(safe).suffix.lower() not in allowed:
        raise HTTPException(status_code=400, detail="File type not allowed")

    root = edit_packs_dir().resolve()
    # zip lives in root; mp4 may live inside a pack folder
    candidates = [root / safe, *root.glob(f"*/{safe}"), *root.glob(f"*/*/{safe}")]
    path = next((p.resolve() for p in candidates if p.is_file()), None)
    if path is None or not str(path).startswith(str(root)):
        raise HTTPException(status_code=404, detail="File not found")

    media = {
        ".zip": "application/zip",
        ".mp4": "video/mp4",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".srt": "application/x-subrip",
        ".json": "application/json",
        ".md": "text/markdown",
        ".mp3": "audio/mpeg",
    }.get(path.suffix.lower(), "application/octet-stream")

    return FileResponse(
        path,
        media_type=media,
        filename=safe,
        content_disposition_type="inline" if inline else "attachment",
    )


def _run_auto_edit_job(
    job_id: str,
    script: str,
    title: str,
    voice_mp3_filename: Optional[str],
    generate_images: bool,
    build_video: bool,
) -> None:
    try:
        job_manager.update(job_id, status="running", step="Starting visual edit pack", progress=0.02)

        def on_progress(step: str, progress: float) -> None:
            job_manager.update(job_id, status="running", step=step, progress=progress)

        result = run_auto_edit_pack(
            script=script,
            title=title,
            voice_mp3_filename=voice_mp3_filename,
            generate_images=generate_images,
            build_video=build_video,
            on_progress=on_progress,
        )
        job_manager.update(
            job_id,
            status="completed",
            step="Edit pack ready",
            progress=1.0,
            result=result,
        )
    except VisualEditError as e:
        job_manager.update(job_id, status="failed", error=str(e))
    except Exception as e:
        job_manager.update(job_id, status="failed", error=str(e)[:500])
