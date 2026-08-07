"""Voice cloning API — sample upload, clone, synthesize selected transcripts."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import get_settings
from app.constants import BATCH_STATUS_VOICE_DONE
from app.models.schemas import (
    JobStatusResponse,
    VoiceCloneCreateResponse,
    VoiceInfo,
    VoiceListResponse,
    VoiceSynthesizeRequest,
    VoiceSynthesizeResponse,
)
from app.services.auth import get_credentials
from app.services.jobs import job_manager
from app.services.output_sheet import (
    is_output_sheet_configured,
    read_output_rows,
    update_output_voice_fields,
)
from app.services.storage import storage
from app.services import voices_db
from app.services.voice_clone import (
    VoiceCloneError,
    create_cloned_voice,
    elevenlabs_configured,
    resolve_voice_output_dir,
    safe_filename,
    synthesize_to_file,
)
from app.services.workers import submit_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])

LANGUAGE_COLUMNS = {
    "English Transcript",
    "British English",
    "American English",
    "Spanish",
    "Chinese (Simplified)",
    "Hindi",
    "Arabic",
    "Portuguese",
    "French",
    "Russian",
    "Japanese",
    "German",
    "Korean",
}


def _voice_info(v: dict) -> VoiceInfo:
    return VoiceInfo(
        id=v["id"],
        name=v["name"],
        provider_voice_id=v["provider_voice_id"],
        created_at=v.get("created_at") or "",
        sample_filename=v.get("sample_filename"),
    )


@router.get("/list", response_model=VoiceListResponse)
def list_voices():
    settings = get_settings()
    cfg = storage.get_admin_config()
    return VoiceListResponse(
        voices=[_voice_info(v) for v in voices_db.list_voices()],
        voice_output_dir=cfg.get("voice_output_dir") or settings.voice_output_dir,
        elevenlabs_configured=elevenlabs_configured(),
    )


@router.post("/clone", response_model=VoiceCloneCreateResponse)
async def clone_voice(
    name: str = Form(...),
    sample: UploadFile = File(...),
):
    if not elevenlabs_configured():
        raise HTTPException(
            status_code=400,
            detail="Set ELEVENLABS_API_KEY in backend .env to enable voice cloning",
        )
    if not name.strip():
        raise HTTPException(status_code=400, detail="Voice name is required")

    # Save sample under uploads
    upload_id = f"voice_{name.strip().replace(' ', '_')}"
    content = await sample.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty sample file")
    filename = sample.filename or "sample.mp3"
    path = storage.save_upload(upload_id, filename, content)

    try:
        entry = create_cloned_voice(name=name.strip(), sample_path=path)
    except VoiceCloneError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return VoiceCloneCreateResponse(voice=_voice_info(entry))


@router.post("/output-dir")
def set_output_dir(body: dict):
    path = (body.get("path") or "").strip()
    if not path:
        raise HTTPException(status_code=400, detail="path is required")
    try:
        resolve_voice_output_dir(path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    storage.save_voice_output_dir(path)
    return {"success": True, "voice_output_dir": path}


@router.post("/synthesize", response_model=VoiceSynthesizeResponse)
def synthesize(body: VoiceSynthesizeRequest):
    if not get_credentials():
        raise HTTPException(status_code=401, detail="Google account not connected")
    if not is_output_sheet_configured():
        raise HTTPException(status_code=400, detail="Output sheet URL is not configured")
    if not elevenlabs_configured():
        raise HTTPException(status_code=400, detail="ELEVENLABS_API_KEY is not set")
    if not body.voice_id:
        raise HTTPException(status_code=400, detail="Select a voice")
    if not body.output_row_indexes:
        raise HTTPException(status_code=400, detail="Select at least one transcript row")
    if body.language_column not in LANGUAGE_COLUMNS:
        raise HTTPException(
            status_code=400,
            detail=f"language_column must be one of: {', '.join(sorted(LANGUAGE_COLUMNS))}",
        )

    voice = voices_db.get_voice(body.voice_id)
    if not voice:
        raise HTTPException(status_code=404, detail="Voice not found — create or select one first")

    job_id = job_manager.create()
    submit_task(
        _run_synthesize_job,
        job_id,
        body.voice_id,
        list(body.output_row_indexes),
        body.language_column,
        body.output_dir,
    )
    return VoiceSynthesizeResponse(job_id=job_id)


@router.get("/status/{job_id}", response_model=JobStatusResponse)
def voice_job_status(job_id: str):
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(**job_manager.to_response(job_id))


@router.delete("/{voice_id}")
def delete_voice(voice_id: str):
    if not voices_db.delete_voice(voice_id):
        raise HTTPException(status_code=404, detail="Voice not found")
    return {"success": True}


def _run_synthesize_job(
    job_id: str,
    voice_id: str,
    row_indexes: list[int],
    language_column: str,
    output_dir: Optional[str],
) -> None:
    try:
        voice = voices_db.get_voice(voice_id)
        if not voice:
            job_manager.update(job_id, status="failed", error="Voice not found")
            return

        out_dir = resolve_voice_output_dir(output_dir)
        if output_dir and output_dir.strip():
            storage.save_voice_output_dir(output_dir.strip())

        rows = {r.row_index: r for r in read_output_rows()}
        total = len(row_indexes)
        done = 0
        files: list[str] = []
        errors: list[dict] = []

        for ri in row_indexes:
            row = rows.get(ri)
            if not row:
                errors.append({"row_index": ri, "error": "Row not found in output sheet"})
                continue

            text = row.cells.get(language_column, "")
            if not text.strip():
                errors.append({"row_index": ri, "error": f"No text in column {language_column}"})
                continue

            job_manager.update(
                job_id,
                status="running",
                step=f"Cloning voice for: {row.video_name}",
                progress=done / max(1, total),
            )

            fname = f"{safe_filename(voice['name'])}__{safe_filename(row.video_name)}__{safe_filename(language_column)}.mp3"
            dest = out_dir / fname
            try:
                synthesize_to_file(
                    provider_voice_id=voice["provider_voice_id"],
                    text=text,
                    output_path=dest,
                )
                note = (
                    f"Voice '{voice['name']}' · language: {language_column} · "
                    f"file: {dest.name}"
                )
                update_output_voice_fields(
                    ri,
                    voice_name=voice["name"],
                    voice_directory=str(out_dir.resolve()),
                    voice_notes=note,
                    status=BATCH_STATUS_VOICE_DONE,
                )
                files.append(str(dest.resolve()))
                done += 1
            except Exception as e:
                logger.exception("TTS failed for row %s", ri)
                errors.append({"row_index": ri, "error": str(e)[:400]})

        job_manager.update(
            job_id,
            status="completed",
            step="Voice cloning complete",
            progress=1.0,
            result={
                "processed": done,
                "failed": len(errors),
                "files": files,
                "output_dir": str(out_dir.resolve()),
                "voice_name": voice["name"],
                "errors": errors,
            },
        )
    except Exception as e:
        job_manager.update(job_id, status="failed", error=str(e))
