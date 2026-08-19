"""Voice cloning API — sample upload, clone, synthesize selected transcripts."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import get_settings
from app.constants import BATCH_STATUS_VOICE_DONE
from app.models.schemas import (
    JobStatusResponse,
    SpeakTextRequest,
    VoiceCloneCreateResponse,
    VoiceCloneFromUrlRequest,
    VoiceCloneFromUrlResponse,
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
    voice_mp3_filename,
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
            detail="Set FISH_API_KEY in backend .env to enable voice cloning",
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


@router.post("/clone-from-url", response_model=VoiceCloneFromUrlResponse)
def clone_voice_from_url(body: VoiceCloneFromUrlRequest):
    """Download audio from a URL, trim a short sample, clone with Fish, save voice."""
    if not elevenlabs_configured():
        raise HTTPException(
            status_code=400,
            detail="Set FISH_API_KEY in backend .env to enable voice cloning",
        )
    url = (body.url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Paste a valid http(s) video/audio URL")

    job_id = job_manager.create()
    submit_task(
        _run_clone_from_url_job,
        job_id,
        url,
        (body.name or "").strip(),
        float(body.start_sec or 0.0),
        float(body.duration_sec or 30.0),
    )
    return VoiceCloneFromUrlResponse(job_id=job_id)


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
        raise HTTPException(status_code=400, detail="FISH_API_KEY is not set")
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


@router.post("/speak-text", response_model=VoiceSynthesizeResponse)
def speak_text(body: SpeakTextRequest):
    """Freeform text → MP3 using any saved/cloned voice (no sheet required)."""
    if not elevenlabs_configured():
        raise HTTPException(status_code=400, detail="FISH_API_KEY is not set")
    if not body.voice_id:
        raise HTTPException(status_code=400, detail="Select a voice")
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Paste some text to speak")
    if len(text) > 120_000:
        raise HTTPException(status_code=400, detail="Text is too long (max ~120k characters)")
    voice = voices_db.get_voice(body.voice_id)
    if not voice:
        raise HTTPException(status_code=404, detail="Voice not found — save a sample first")

    job_id = job_manager.create()
    submit_task(
        _run_speak_text_job,
        job_id,
        body.voice_id,
        text,
        (body.title or "spoken").strip() or "spoken",
        body.output_dir,
    )
    return VoiceSynthesizeResponse(job_id=job_id)


@router.get("/download/{filename}")
def download_voice_file(filename: str, inline: bool = False):
    """Serve an MP3 from the voice output folder.

    Use ``?inline=1`` for in-browser preview (audio player).
    Default is attachment so the file only saves when the user downloads.
    """
    from fastapi.responses import FileResponse

    safe = Path(filename).name
    if safe != filename or ".." in filename or not safe.lower().endswith(".mp3"):
        raise HTTPException(status_code=400, detail="Invalid filename")
    out_dir = resolve_voice_output_dir()
    path = (out_dir / safe).resolve()
    if not str(path).startswith(str(out_dir.resolve())) or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path,
        media_type="audio/mpeg",
        filename=safe,
        content_disposition_type="inline" if inline else "attachment",
    )


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

        for idx, ri in enumerate(row_indexes):
            row = rows.get(ri)
            if not row:
                errors.append({"row_index": ri, "error": "Row not found in output sheet"})
                continue

            text = row.cells.get(language_column, "")
            if not text.strip():
                errors.append({"row_index": ri, "error": f"No text in column {language_column}"})
                continue

            base = idx / max(1, total)
            span = 1.0 / max(1, total)

            def _tts_progress(frac: float, msg: str, *, _base=base, _span=span, _name=row.video_name) -> None:
                job_manager.update(
                    job_id,
                    status="running",
                    step=f"{_name}: {msg}",
                    progress=min(0.99, _base + max(0.0, min(1.0, frac)) * _span),
                )

            job_manager.update(
                job_id,
                status="running",
                step=f"{row.video_name}: starting Fish TTS ({len(text)} chars)",
                progress=base,
            )

            fname = voice_mp3_filename(voice["name"], row.video_name, language_column)
            dest = out_dir / fname
            try:
                synthesize_to_file(
                    provider_voice_id=voice["provider_voice_id"],
                    text=text,
                    output_path=dest,
                    on_progress=_tts_progress,
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
                job_manager.update(
                    job_id,
                    status="running",
                    step=f"Saved {row.video_name}",
                    progress=min(0.99, (idx + 1) / max(1, total)),
                )
            except Exception as e:
                logger.exception("TTS failed for row %s", ri)
                errors.append({"row_index": ri, "error": str(e)[:400]})

        filenames = [Path(f).name for f in files]
        job_manager.update(
            job_id,
            status="completed",
            step="Voice cloning complete",
            progress=1.0,
            result={
                "processed": done,
                "failed": len(errors),
                "files": files,
                "filenames": filenames,
                "output_dir": str(out_dir.resolve()),
                "voice_name": voice["name"],
                "errors": errors,
            },
        )
    except Exception as e:
        job_manager.update(job_id, status="failed", error=str(e))


def _run_speak_text_job(
    job_id: str,
    voice_id: str,
    text: str,
    title: str,
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

        def _tts_progress(frac: float, msg: str) -> None:
            job_manager.update(
                job_id,
                status="running",
                step=msg,
                progress=min(0.99, max(0.0, frac)),
            )

        job_manager.update(
            job_id,
            status="running",
            step=f"Starting TTS ({len(text)} chars)",
            progress=0.02,
        )

        fname = voice_mp3_filename(voice["name"], title)
        dest = out_dir / fname
        synthesize_to_file(
            provider_voice_id=voice["provider_voice_id"],
            text=text,
            output_path=dest,
            on_progress=_tts_progress,
        )
        job_manager.update(
            job_id,
            status="completed",
            step="MP3 ready",
            progress=1.0,
            result={
                "processed": 1,
                "failed": 0,
                "files": [str(dest.resolve())],
                "filename": dest.name,
                "title": title,
                "output_dir": str(out_dir.resolve()),
                "voice_name": voice["name"],
                "download_url": f"/api/voice/download/{dest.name}",
                "errors": [],
            },
        )
    except Exception as e:
        logger.exception("speak-text failed")
        job_manager.update(job_id, status="failed", error=str(e))


def _run_clone_from_url_job(
    job_id: str,
    url: str,
    name: str,
    start_sec: float,
    duration_sec: float,
) -> None:
    try:
        from app.services.media_bins import prepare_voice_sample_from_url

        job_manager.update(
            job_id,
            status="running",
            step="Downloading audio from URL…",
            progress=0.08,
        )
        sample_path, source_title = prepare_voice_sample_from_url(
            url,
            start_sec=start_sec,
            duration_sec=duration_sec,
        )
        voice_name = name.strip() or source_title.strip() or "URL voice"
        job_manager.update(
            job_id,
            status="running",
            step=f"Cloning voice from sample ({sample_path.name})…",
            progress=0.55,
        )
        entry = create_cloned_voice(
            name=voice_name,
            sample_path=str(sample_path),
            description=f"Cloned from URL sample ({source_title})",
        )
        job_manager.update(
            job_id,
            status="completed",
            step="Voice cloned and saved",
            progress=1.0,
            result={
                "voice": {
                    "id": entry["id"],
                    "name": entry["name"],
                    "provider_voice_id": entry["provider_voice_id"],
                    "created_at": entry.get("created_at") or "",
                    "sample_filename": entry.get("sample_filename"),
                },
                "sample_path": str(sample_path.resolve()),
                "sample_filename": sample_path.name,
                "source_title": source_title,
                "source_url": url,
                "start_sec": start_sec,
                "duration_sec": duration_sec,
            },
        )
    except VoiceCloneError as e:
        job_manager.update(job_id, status="failed", error=str(e))
    except Exception as e:
        logger.exception("clone-from-url failed")
        job_manager.update(job_id, status="failed", error=str(e)[:500])
