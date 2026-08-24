import time

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import get_settings
from app.models.schemas import (
    JobStatusResponse,
    TranscribeRequest,
    TranscribeResponse,
    UploadCompleteRequest,
    UploadInitRequest,
    UploadInitResponse,
    UploadResponse,
)
from app.services.detect_source import validate_local_path
from app.services.jobs import job_manager
from app.services.prefetch import prefetch_manager
from app.services.storage import storage
from app.services.transcribe import schedule_whisper_preload, transcribe_source
from app.services.video import VideoError
from app.services.workers import submit_task

router = APIRouter(prefix="/api", tags=["transcribe"])


def _resolve_upload_path(upload_id: str) -> str | None:
    matches = list(storage.uploads_dir.glob(f"{upload_id}_*"))
    return str(matches[0]) if matches else None


def _resolve_prefetch(
    prefetch_cache_id: str | None,
    *,
    wait_seconds: int = 300,
) -> tuple[str | None, float | None]:
    if not prefetch_cache_id:
        return None, None

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        entry = prefetch_manager.get(prefetch_cache_id)
        if not entry:
            return None, None
        if entry.status == "ready" and entry.audio_path:
            return entry.audio_path, entry.duration
        if entry.status == "failed":
            return None, None
        if entry.status != "downloading":
            break
        time.sleep(1.5)

    entry = prefetch_manager.get(prefetch_cache_id)
    if entry and entry.status == "ready" and entry.audio_path:
        return entry.audio_path, entry.duration
    return None, None


def _run_transcription(
    job_id: str,
    source: str,
    source_type: str,
    language: str | None,
    upload_path: str | None,
    prefetch_cache_id: str | None,
) -> None:
    try:
        job_manager.update(job_id, status="running", step="Preparing audio", progress=0.0)

        prepared_audio, prepared_duration = _resolve_prefetch(prefetch_cache_id)

        def on_progress(step: str, progress: float) -> None:
            job_manager.update(job_id, step=step, progress=progress)

        result = transcribe_source(
            source,
            source_type,
            language,
            upload_path,
            on_progress,
            prepared_audio_path=prepared_audio,
            prepared_duration=prepared_duration,
        )
        job_manager.update(job_id, status="completed", step="Done", progress=1.0, result=result)
    except VideoError as e:
        job_manager.update(job_id, status="failed", error=str(e))
    except Exception as e:
        job_manager.update(job_id, status="failed", error=f"Transcription failed: {e}")


@router.post("/transcribe/warmup")
def transcribe_warmup():
    """Preload Whisper model in background (call when user picks a video)."""
    submit_task(schedule_whisper_preload)
    return {"status": "warming"}


@router.post("/transcribe", response_model=TranscribeResponse)
def transcribe_endpoint(body: TranscribeRequest):
    upload_path = None
    if body.upload_id:
        upload_path = _resolve_upload_path(body.upload_id)
        if not upload_path:
            raise HTTPException(status_code=400, detail="Upload not found")

    if body.type == "local" and not upload_path:
        valid, msg = validate_local_path(body.source)
        if not valid:
            raise HTTPException(status_code=400, detail=msg)

    job_id = job_manager.create()
    submit_task(
        _run_transcription,
        job_id,
        body.source,
        body.type,
        body.language,
        upload_path,
        body.prefetch_cache_id,
    )

    return TranscribeResponse(
        transcript="", segments=[], language="", duration=0, job_id=job_id
    )


@router.post("/transcribe/sync", response_model=TranscribeResponse)
def transcribe_sync_endpoint(body: TranscribeRequest):
    upload_path = None
    if body.upload_id:
        upload_path = _resolve_upload_path(body.upload_id)
        if not upload_path:
            raise HTTPException(status_code=400, detail="Upload not found")

    if body.type == "local" and not upload_path:
        valid, msg = validate_local_path(body.source)
        if not valid:
            raise HTTPException(status_code=400, detail=msg)

    try:
        prepared_audio, prepared_duration = _resolve_prefetch(body.prefetch_cache_id)
        result = transcribe_source(
            body.source,
            body.type,
            body.language,
            upload_path,
            prepared_audio_path=prepared_audio,
            prepared_duration=prepared_duration,
        )
        return TranscribeResponse(**result)
    except VideoError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}") from e


@router.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
def job_status(job_id: str, include_result: bool = True):
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(**job_manager.to_response(job_id, include_result=include_result))


@router.get("/jobs/{job_id}/result")
def job_result(job_id: str):
    """Return completed job payload.

    Transcription jobs return TranscribeResponse-shaped data.
    Voice / edit jobs return their own result dict.
    """
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed" or not job.result:
        raise HTTPException(status_code=409, detail="Job result not ready yet")
    result = job.result
    # Prefer typed transcript response when shape matches
    if isinstance(result, dict) and "transcript" in result and "segments" in result:
        return TranscribeResponse(**result)
    return result


@router.post("/upload", response_model=UploadResponse)
async def upload_video_file(file: UploadFile = File(...)):
    import uuid

    upload_id = str(uuid.uuid4())
    content = await file.read()
    path = storage.save_upload(upload_id, file.filename or "video.mp4", content)
    return UploadResponse(upload_id=upload_id, filename=file.filename or "video.mp4", path=path)


@router.post("/upload/init", response_model=UploadInitResponse)
def upload_init(body: UploadInitRequest):
    import uuid

    settings = get_settings()
    upload_id = str(uuid.uuid4())
    filename = body.filename or "video.mp4"
    storage.init_partial_upload(upload_id, filename, max(0, body.size))
    return UploadInitResponse(upload_id=upload_id, chunk_size=settings.upload_chunk_size)


@router.put("/upload/{upload_id}/chunk/{chunk_index}")
async def upload_chunk(upload_id: str, chunk_index: int, file: UploadFile = File(...)):
    try:
        session = storage.get_upload_session(upload_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="Upload session not found") from e
    filename = session["filename"]
    offset = chunk_index * get_settings().upload_chunk_size
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty chunk")
    try:
        storage.write_upload_chunk(upload_id, filename, offset, data)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="Upload file missing — restart upload") from e
    return {"ok": True, "chunk_index": chunk_index, "bytes": len(data)}


@router.post("/upload/complete", response_model=UploadResponse)
def upload_complete(body: UploadCompleteRequest):
    try:
        path = storage.finalize_partial_upload(body.upload_id, body.filename)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="Upload not found or incomplete") from e
    return UploadResponse(upload_id=body.upload_id, filename=body.filename, path=path)
