"""Batch: input sheet → transcribe → translate → categorize → Google Doc → output sheet."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Literal, Optional

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.constants import (
    BATCH_STATUS_DONE,
    BATCH_STATUS_FAILED,
    BATCH_STATUS_PENDING,
    BATCH_STATUS_PROCESSING,
    BATCH_STATUS_VOICE_READY,
)
from app.models.schemas import (
    BatchConfigResponse,
    BatchQueueResponse,
    BatchRowResponse,
    BatchRunResponse,
    JobStatusResponse,
    MarkDoneRequest,
    MarkDoneResponse,
    OutputQueueResponse,
    OutputRowResponse,
)
from app.services.auth import get_credentials
from app.services.category import classify_category
from app.services.detect_source import detect_source, validate_local_path, validate_online_url
from app.services.english_variants import make_american, make_british
from app.services.input_sheet import (
    QueueRow,
    is_input_sheet_configured,
    normalize_queue_status,
    read_queue,
    resolve_input_sheet_url,
    update_row_status,
)
from app.services.jobs import job_manager
from app.services.multilang import ensure_english, translate_all_languages
from app.services.output_sheet import (
    OutputRowData,
    append_output_row,
    format_duration,
    is_output_sheet_configured,
    mark_rows_done,
    now_transcribed,
    read_output_rows,
    resolve_output_sheet_url,
    ensure_output_headers,
)
from app.services.storage import storage
from app.services.transcribe import transcribe_source
from app.services.transcript_doc import create_transcript_doc
from app.services.video import VideoError
from app.services.voice_clone import elevenlabs_configured
from app.services.workers import submit_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/batch", tags=["batch"])

_batch_lock_job_id: Optional[str] = None
_transcribe_lock = threading.Lock()
_output_write_lock = threading.Lock()


def _clear_stale_batch_lock() -> None:
    global _batch_lock_job_id
    if not _batch_lock_job_id:
        return
    existing = job_manager.get(_batch_lock_job_id)
    if not existing or existing.status not in ("pending", "running"):
        _batch_lock_job_id = None


def _is_job_cancelled(job_id: str) -> bool:
    job = job_manager.get(job_id)
    return job is None or job.status == "failed"


def _row_to_response(row: QueueRow) -> BatchRowResponse:
    return BatchRowResponse(
        row_index=row.row_index,
        program_title=row.program_title,
        video_path=row.video_path,
        status=row.status,
        error=row.error or None,
    )


@router.get("/config", response_model=BatchConfigResponse)
def batch_config():
    settings = get_settings()
    input_url = resolve_input_sheet_url()
    output_url = resolve_output_sheet_url()
    workers = max(1, min(8, settings.batch_workers))
    cfg = storage.get_admin_config()
    return BatchConfigResponse(
        input_sheet_configured=is_input_sheet_configured(),
        output_sheet_configured=is_output_sheet_configured(),
        input_sheet_url_masked="••••••••••" if input_url else "",
        output_sheet_url_masked="••••••••••" if output_url else "",
        input_sheet_url=input_url,
        output_sheet_url=output_url,
        google_connected=get_credentials() is not None,
        batch_workers=workers,
        elevenlabs_configured=elevenlabs_configured(),
        voice_output_dir=cfg.get("voice_output_dir") or settings.voice_output_dir,
    )


@router.get("/queue", response_model=BatchQueueResponse)
def batch_queue():
    if not get_credentials():
        raise HTTPException(status_code=401, detail="Google account not connected")
    if not is_input_sheet_configured():
        raise HTTPException(status_code=400, detail="Input sheet URL is not configured")

    try:
        rows = read_queue(include_non_pending=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    pending = sum(1 for r in rows if normalize_queue_status(r.status) == BATCH_STATUS_PENDING)
    processing = sum(1 for r in rows if normalize_queue_status(r.status) == BATCH_STATUS_PROCESSING)
    done = sum(1 for r in rows if normalize_queue_status(r.status) == BATCH_STATUS_DONE)
    failed = sum(1 for r in rows if normalize_queue_status(r.status) == BATCH_STATUS_FAILED)
    return BatchQueueResponse(
        rows=[_row_to_response(r) for r in rows],
        pending_count=pending,
        processing_count=processing,
        done_count=done,
        failed_count=failed,
        total_count=len(rows),
        input_sheet_url=resolve_input_sheet_url(),
        output_sheet_url=resolve_output_sheet_url(),
    )


@router.get("/output", response_model=OutputQueueResponse)
def output_queue():
    if not get_credentials():
        raise HTTPException(status_code=401, detail="Google account not connected")
    if not is_output_sheet_configured():
        raise HTTPException(status_code=400, detail="Output sheet URL is not configured")

    try:
        rows = read_output_rows()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    ready = sum(1 for r in rows if r.status == BATCH_STATUS_VOICE_READY)
    cloned = sum(1 for r in rows if r.status == "voice_cloned")
    marked = sum(1 for r in rows if r.status == "marked_done")
    return OutputQueueResponse(
        rows=[
            OutputRowResponse(
                row_index=r.row_index,
                video_name=r.video_name,
                source_video=r.source_video,
                category=r.category,
                video_length=r.video_length,
                date_transcribed=r.date_transcribed,
                docs_link=r.docs_link,
                status=r.status,
                voice_name=r.voice_name,
                voice_directory=r.voice_directory,
                voice_notes=r.voice_notes,
                error=r.error or None,
            )
            for r in rows
        ],
        ready_for_voice_count=ready,
        voice_cloned_count=cloned,
        marked_done_count=marked,
        total_count=len(rows),
        output_sheet_url=resolve_output_sheet_url(),
    )


@router.post("/mark-done", response_model=MarkDoneResponse)
def mark_done(body: MarkDoneRequest):
    if not get_credentials():
        raise HTTPException(status_code=401, detail="Google account not connected")
    if not is_output_sheet_configured():
        raise HTTPException(status_code=400, detail="Output sheet URL is not configured")
    if not body.output_row_indexes:
        raise HTTPException(status_code=400, detail="Select at least one output row")
    try:
        updated = mark_rows_done(body.output_row_indexes)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return MarkDoneResponse(updated=updated)


@router.post("/run", response_model=BatchRunResponse)
def start_batch():
    global _batch_lock_job_id

    _clear_stale_batch_lock()

    if not get_credentials():
        raise HTTPException(status_code=401, detail="Google account not connected")
    if not is_input_sheet_configured():
        raise HTTPException(status_code=400, detail="Input sheet URL is not configured")
    if not is_output_sheet_configured():
        raise HTTPException(status_code=400, detail="Output sheet URL is not configured")

    if _batch_lock_job_id:
        existing = job_manager.get(_batch_lock_job_id)
        if existing and existing.status in ("pending", "running"):
            raise HTTPException(status_code=409, detail="A batch job is already running")

    try:
        pending_rows = [r for r in read_queue(include_non_pending=False) if r.status == BATCH_STATUS_PENDING]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if not pending_rows:
        raise HTTPException(status_code=400, detail="No pending rows in the input sheet")

    settings = get_settings()
    workers = max(1, min(8, settings.batch_workers))

    job_id = job_manager.create()
    _batch_lock_job_id = job_id
    submit_task(_run_batch_job, job_id)
    return BatchRunResponse(job_id=job_id, pending_count=len(pending_rows), batch_workers=workers)


@router.post("/reset")
def reset_batch():
    global _batch_lock_job_id

    cleared_lock = False
    if _batch_lock_job_id:
        job = job_manager.get(_batch_lock_job_id)
        if job and job.status in ("pending", "running"):
            job_manager.update(
                _batch_lock_job_id,
                status="failed",
                error="Batch stopped by user reset.",
            )
        _batch_lock_job_id = None
        cleared_lock = True

    sheet_reset = 0
    try:
        if is_input_sheet_configured() and get_credentials():
            for row in read_queue(include_non_pending=True):
                if row.status == BATCH_STATUS_PROCESSING:
                    update_row_status(row.row_index, BATCH_STATUS_PENDING, "")
                    sheet_reset += 1
    except Exception as e:
        logger.warning("Could not reset processing rows in sheet: %s", e)

    return {
        "success": True,
        "cleared_lock": cleared_lock,
        "sheet_rows_reset": sheet_reset,
    }


@router.get("/status/{job_id}", response_model=JobStatusResponse)
def batch_status(job_id: str):
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(**job_manager.to_response(job_id))


def _process_row(
    row: QueueRow,
    on_progress: Callable[[str, float], None],
    *,
    job_id: str,
    index: int,
    total: int,
) -> Literal["ok", "cancelled"]:
    if _is_job_cancelled(job_id):
        return "cancelled"

    if not row.program_title.strip():
        raise ValueError("Video Name is empty")
    if not row.video_path.strip():
        raise ValueError("Video Path is empty")

    update_row_status(row.row_index, BATCH_STATUS_PROCESSING, "Transcribing…")

    detected = detect_source(row.video_path)
    if not detected["valid"] or not detected["type"]:
        raise ValueError(detected.get("message") or "Could not detect video source")

    source = detected["normalized"]
    source_type = detected["type"]

    if source_type == "local":
        valid, msg = validate_local_path(source)
        if not valid:
            raise ValueError(msg)
    else:
        valid, msg = validate_online_url(source)
        if not valid:
            raise ValueError(msg)

    base_progress = index / max(1, total)
    span = 1.0 / max(1, total)

    def tx_progress(step: str, pct: float) -> None:
        on_progress(
            f"[{index + 1}/{total}] {row.program_title}: {step}",
            base_progress + pct * span * 0.35,
        )

    on_progress(f"[{index + 1}/{total}] Transcribing: {row.program_title}", base_progress)

    with _transcribe_lock:
        if _is_job_cancelled(job_id):
            update_row_status(row.row_index, BATCH_STATUS_PENDING, "")
            return "cancelled"
        tx = transcribe_source(source, source_type, on_progress=tx_progress)

    transcript = tx["transcript"]
    detected_lang = tx.get("language") or "en"
    duration = float(tx.get("duration") or 0.0)

    if _is_job_cancelled(job_id):
        update_row_status(row.row_index, BATCH_STATUS_PENDING, "")
        return "cancelled"

    update_row_status(row.row_index, BATCH_STATUS_PROCESSING, "Preparing English…")
    on_progress(
        f"[{index + 1}/{total}] English + variants: {row.program_title}",
        base_progress + span * 0.4,
    )
    english = ensure_english(transcript, detected_lang)
    british = make_british(english)
    american = make_american(english)

    if _is_job_cancelled(job_id):
        update_row_status(row.row_index, BATCH_STATUS_PENDING, "")
        return "cancelled"

    update_row_status(row.row_index, BATCH_STATUS_PROCESSING, "Translating languages…")
    on_progress(
        f"[{index + 1}/{total}] Translating: {row.program_title}",
        base_progress + span * 0.5,
    )

    def lang_progress(msg: str, pct: float) -> None:
        on_progress(
            f"[{index + 1}/{total}] {row.program_title}: {msg}",
            base_progress + span * (0.5 + 0.2 * pct),
        )

    translations = translate_all_languages(english, on_progress=lang_progress)

    if _is_job_cancelled(job_id):
        update_row_status(row.row_index, BATCH_STATUS_PENDING, "")
        return "cancelled"

    update_row_status(row.row_index, BATCH_STATUS_PROCESSING, "Classifying category…")
    category = classify_category(row.program_title, english)
    length_str = format_duration(duration)
    date_str = now_transcribed()

    update_row_status(row.row_index, BATCH_STATUS_PROCESSING, "Creating Google Doc…")
    on_progress(
        f"[{index + 1}/{total}] Google Doc: {row.program_title}",
        base_progress + span * 0.8,
    )
    _, doc_url = create_transcript_doc(
        video_name=row.program_title,
        source_video=row.video_path,
        english=english,
        british=british,
        american=american,
        translations=translations,
        detected_language=detected_lang,
        category=category,
        video_length=length_str,
    )

    if _is_job_cancelled(job_id):
        update_row_status(row.row_index, BATCH_STATUS_PENDING, "")
        return "cancelled"

    update_row_status(row.row_index, BATCH_STATUS_PROCESSING, "Writing output sheet…")
    on_progress(
        f"[{index + 1}/{total}] Output sheet: {row.program_title}",
        base_progress + span * 0.92,
    )

    with _output_write_lock:
        append_output_row(
            OutputRowData(
                video_name=row.program_title,
                source_video=row.video_path,
                english=english,
                british=british,
                american=american,
                translations=translations,
                category=category,
                video_length=length_str,
                date_transcribed=date_str,
                detected_language=detected_lang,
                docs_link=doc_url,
                status=BATCH_STATUS_VOICE_READY,
            )
        )

    update_row_status(row.row_index, BATCH_STATUS_DONE, "")
    return "ok"


def _run_batch_job(job_id: str) -> None:
    global _batch_lock_job_id

    settings = get_settings()
    workers = max(1, min(8, settings.batch_workers))
    progress_lock = threading.Lock()
    finished_count = 0

    def on_progress(step: str, progress: float) -> None:
        job_manager.update(job_id, status="running", step=step, progress=min(0.99, progress))

    def bump_progress(message: str) -> None:
        nonlocal finished_count
        with progress_lock:
            finished_count += 1
            done = finished_count
        on_progress(
            f"{message} ({done} finished)",
            min(0.99, done / max(1, total)),
        )

    try:
        job_manager.update(
            job_id,
            status="running",
            step=f"Loading queue ({workers} parallel workers)",
            progress=0.01,
        )
        ensure_output_headers()
        rows = [r for r in read_queue(include_non_pending=False) if r.status == BATCH_STATUS_PENDING]
        total = len(rows)
        if total == 0:
            job_manager.update(
                job_id,
                status="completed",
                step="No pending rows",
                progress=1.0,
                result={
                    "processed": 0,
                    "failed": 0,
                    "output_sheet_url": resolve_output_sheet_url(),
                },
            )
            return

        processed = 0
        failed = 0
        cancelled = 0
        errors: list[dict] = []

        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="batch") as pool:
            futures = {
                pool.submit(
                    _process_row,
                    row,
                    on_progress,
                    job_id=job_id,
                    index=i,
                    total=total,
                ): row
                for i, row in enumerate(rows)
            }

            for future in as_completed(futures):
                row = futures[future]
                if _is_job_cancelled(job_id):
                    cancelled += 1
                    continue

                try:
                    outcome = future.result()
                    if outcome == "ok":
                        processed += 1
                        bump_progress(f"Completed {row.program_title}")
                    elif outcome == "cancelled":
                        cancelled += 1
                    else:
                        failed += 1
                except (VideoError, ValueError) as e:
                    failed += 1
                    err_msg = str(e)[:500]
                    update_row_status(row.row_index, BATCH_STATUS_FAILED, err_msg)
                    errors.append(
                        {"row_index": row.row_index, "program_title": row.program_title, "error": err_msg}
                    )
                    bump_progress(f"Failed {row.program_title}")
                    logger.exception("Batch row %s failed", row.row_index)
                except Exception as e:
                    failed += 1
                    err_msg = str(e)[:500]
                    update_row_status(row.row_index, BATCH_STATUS_FAILED, err_msg)
                    errors.append(
                        {"row_index": row.row_index, "program_title": row.program_title, "error": err_msg}
                    )
                    bump_progress(f"Failed {row.program_title}")
                    logger.exception("Batch row %s failed unexpectedly", row.row_index)

        if _is_job_cancelled(job_id):
            job_manager.update(
                job_id,
                status="failed",
                error="Batch stopped by user reset.",
                step="Batch stopped",
            )
            return

        job_manager.update(
            job_id,
            status="completed",
            step="Batch complete — ready for voice cloning",
            progress=1.0,
            result={
                "processed": processed,
                "failed": failed,
                "cancelled": cancelled,
                "total": total,
                "workers": workers,
                "errors": errors,
                "output_sheet_url": resolve_output_sheet_url(),
            },
        )
    except Exception as e:
        job_manager.update(job_id, status="failed", error=str(e))
    finally:
        if _batch_lock_job_id == job_id:
            _batch_lock_job_id = None
