import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable, Optional

from fastapi import APIRouter, HTTPException

from app.config import get_settings

logger = logging.getLogger(__name__)

from app.constants import YOUTUBE_POPULAR_LANGUAGES
from app.models.schemas import (
    AutoPipelineRunRequest,
    AutoPipelineRunResponse,
    PipelineFinishRequest,
    PipelineFinishStartResponse,
    PipelineRunRequest,
    PipelineRunResponse,
)
from app.routers.transcribe import _resolve_prefetch
from app.services.auth import get_credentials
from app.services.detect_source import validate_local_path
from app.services.google_integrations import (
    append_to_sheet,
    create_google_doc,
    create_google_doc_multilingual,
    derive_video_title,
    ensure_registry_spreadsheet,
    finalize_doc_and_sheet,
    build_google_services,
)
from app.services.jobs import job_manager
from app.services.storage import storage
from app.services.transcribe import transcribe_source
from app.services.translate import translate_text
from app.services.video import VideoError
from app.services.workers import submit_task

router = APIRouter(prefix="/api", tags=["pipeline"])


def _resolve_upload_path(upload_id: str) -> tuple[str | None, str | None]:
    matches = list(storage.uploads_dir.glob(f"{upload_id}_*"))
    if not matches:
        return None, None
    path = str(matches[0])
    filename = matches[0].name.split("_", 1)[1] if "_" in matches[0].name else matches[0].name
    return path, filename


def _normalize_lang(code: str) -> str:
    return code.lower().split("-")[0]


def _translation_targets(
    source_language: str,
    selected_codes: Optional[list[str]] = None,
) -> list[tuple[str, str]]:
    """Return only explicitly selected languages. Empty list = no translation."""
    if not selected_codes:
        return []

    source_norm = _normalize_lang(source_language)
    targets: list[tuple[str, str]] = []
    seen: set[str] = set()
    selected_norm = {_normalize_lang(c) for c in selected_codes}

    for code, name in YOUTUBE_POPULAR_LANGUAGES:
        norm = _normalize_lang(code)
        if norm == source_norm or norm in seen:
            continue
        if norm not in selected_norm:
            continue
        seen.add(norm)
        targets.append((code, name))
    return targets


def _translate_languages_parallel(
    transcript: str,
    detected_language: str,
    targets: list[tuple[str, str]],
    on_language_done: Optional[Callable[[str, int, int], None]] = None,
) -> dict[str, str]:
    if not targets:
        return {}

    settings = get_settings()
    workers = max(1, min(settings.translate_workers, len(targets)))
    translations: dict[str, str] = {}

    def _one(code: str, name: str) -> tuple[str, str | None]:
        try:
            translated, _ = translate_text(transcript, code, detected_language)
            if translated.strip():
                return name, translated
        except Exception:
            pass
        return name, None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_one, code, name): name for code, name in targets}
        for future in as_completed(futures):
            name, text = future.result()
            if text:
                translations[name] = text
                if on_language_done:
                    on_language_done(name, len(translations), len(targets))

    return translations


def _finish_auto_pipeline(
    *,
    source: str,
    transcript: str,
    detected_language: str,
    duration: float,
    title: Optional[str] = None,
    upload_filename: Optional[str] = None,
    target_languages: Optional[list[str]] = None,
    on_progress: Optional[Callable[[str, float], None]] = None,
) -> AutoPipelineRunResponse:
    if on_progress:
        on_progress("Preparing Google registry…", 0.05)

    try:
        sheet_url = ensure_registry_spreadsheet()
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to prepare registry sheet: {e}") from e

    resolved_title = title or derive_video_title(
        source,
        upload_filename=upload_filename,
    )

    translations: dict[str, str] = {}
    targets = _translation_targets(detected_language, target_languages)

    if targets:
        if on_progress:
            on_progress(f"Translating into {len(targets)} language(s)…", 0.12)

        def _lang_done(name: str, done: int, total: int) -> None:
            if on_progress:
                on_progress(
                    f"Translated {name} ({done}/{total})",
                    0.12 + 0.68 * (done / max(1, total)),
                )

        logger.info(
            "Pipeline finish: translating into %d languages (%d workers)",
            len(targets),
            get_settings().translate_workers,
        )
        translations = _translate_languages_parallel(
            transcript, detected_language, targets, on_language_done=_lang_done
        )
        if not translations:
            raise HTTPException(
                status_code=500,
                detail="Translation produced no results. Check your internet connection or try fewer languages.",
            )
    elif on_progress:
        on_progress("Skipping translation — saving original transcript only", 0.5)

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M UTC")
    admin_cfg = storage.get_admin_config()

    if on_progress:
        on_progress("Creating Google Doc…", 0.85)

    try:
        docs_service, drive_service = build_google_services()
        doc_progress = (
            (lambda step, p: on_progress(step, p)) if on_progress else None
        )
        if translations:
            doc_id, doc_url = create_google_doc_multilingual(
                title=resolved_title,
                transcript=transcript,
                translations=translations,
                source_language=detected_language,
                date=date_str,
                time=time_str,
                source_video=source,
                folder_id=None,
                on_progress=doc_progress,
            )
            language_label = f"{detected_language} + {len(translations)} translations"
        else:
            doc_id, doc_url = create_google_doc(
                title=resolved_title,
                transcript=transcript,
                date=date_str,
                time=time_str,
                source_video=source,
                language=detected_language,
                folder_id=None,
                on_progress=doc_progress,
            )
            language_label = detected_language
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create Google Doc: {e}") from e

    sheet_logged = False
    sheet_warning: str | None = None
    if on_progress:
        on_progress("Logging to registry sheet…", 0.95)
    try:
        sheet_url = finalize_doc_and_sheet(
            drive_service=drive_service,
            doc_id=doc_id,
            folder_id=admin_cfg.get("docs_folder_id"),
            sheet_url=sheet_url,
            title=resolved_title,
            doc_url=doc_url,
            date=date_str,
            time=time_str,
            source_video=source,
            language_label=language_label,
        )
        sheet_logged = True
    except Exception as e:
        sheet_warning = f"Google Doc saved, but registry sheet failed: {e}"

    return AutoPipelineRunResponse(
        title=resolved_title,
        transcript=transcript,
        translations=translations,
        detected_language=detected_language,
        doc_url=doc_url,
        sheet_url=sheet_url,
        sheet_logged=sheet_logged,
        sheet_warning=sheet_warning,
        duration=duration,
    )


@router.post("/pipeline/run", response_model=PipelineRunResponse)
def run_pipeline(body: PipelineRunRequest):
    if not get_credentials():
        raise HTTPException(status_code=401, detail="Google account not connected")

    upload_path = None
    if body.upload_id:
        upload_path, _ = _resolve_upload_path(body.upload_id)
        if not upload_path:
            raise HTTPException(status_code=400, detail="Upload not found")

    if body.type == "local" and not upload_path:
        valid, msg = validate_local_path(body.source)
        if not valid:
            raise HTTPException(status_code=400, detail=msg)

    try:
        tx = transcribe_source(body.source, body.type, body.source_language, upload_path)
    except VideoError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    transcript = tx["transcript"]
    translated_text = None
    language = tx["language"]

    if body.target_language and body.target_language != "none":
        translated_text, _ = translate_text(transcript, body.target_language, tx["language"])
        language = body.target_language

    final_text = translated_text or transcript
    admin_cfg = storage.get_admin_config()

    doc_id, doc_url = create_google_doc(
        title=body.title,
        transcript=final_text,
        date=body.date,
        time=body.time,
        source_video=body.source,
        language=language,
        notes=body.notes,
        folder_id=admin_cfg.get("docs_folder_id"),
    )

    sheet_logged = False
    if body.log_to_sheet and admin_cfg.get("sheet_url"):
        try:
            append_to_sheet(
                sheet_url=admin_cfg["sheet_url"],
                title=body.title,
                doc_url=doc_url,
                date=body.date,
                time=body.time,
                source_video=body.source,
                language=language,
            )
            sheet_logged = True
        except Exception:
            pass

    return PipelineRunResponse(
        transcript=transcript,
        translated_text=translated_text,
        doc_url=doc_url,
        sheet_logged=sheet_logged,
        language=language,
        duration=tx["duration"],
    )


@router.post("/pipeline/auto", response_model=AutoPipelineRunResponse)
def run_auto_pipeline(body: AutoPipelineRunRequest):
    """Transcribe, translate to popular YouTube languages, save Doc + registry Sheet."""
    if not get_credentials():
        raise HTTPException(status_code=401, detail="Connect your Google account first")

    upload_path = None
    upload_filename = None
    if body.upload_id:
        upload_path, upload_filename = _resolve_upload_path(body.upload_id)
        if not upload_path:
            raise HTTPException(status_code=400, detail="Upload not found")

    if body.type == "local" and not upload_path:
        valid, msg = validate_local_path(body.source)
        if not valid:
            raise HTTPException(status_code=400, detail=msg)

    try:
        sheet_url = ensure_registry_spreadsheet()
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to prepare registry sheet: {e}") from e

    try:
        prepared_audio, prepared_duration = _resolve_prefetch(body.prefetch_cache_id)
        logger.info(
            "Pipeline auto: transcribing source=%s type=%s upload=%s",
            body.source,
            body.type,
            bool(upload_path),
        )
        tx = transcribe_source(
            body.source,
            body.type,
            body.source_language,
            upload_path,
            prepared_audio_path=prepared_audio,
            prepared_duration=prepared_duration,
        )
        logger.info(
            "Pipeline auto: transcription done (%.0fs audio, lang=%s)",
            tx.get("duration") or 0,
            tx.get("language"),
        )
    except VideoError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    transcript = tx["transcript"]
    detected_language = tx["language"]
    title = derive_video_title(
        body.source,
        preview_title=body.title,
        upload_filename=upload_filename,
    )

    return _finish_auto_pipeline(
        source=body.source,
        transcript=transcript,
        detected_language=detected_language,
        duration=tx["duration"],
        title=title,
        upload_filename=upload_filename,
    )


@router.get("/pipeline/languages")
def list_pipeline_languages():
    """Popular YouTube languages available for translation."""
    return {
        "languages": [{"code": code, "name": name} for code, name in YOUTUBE_POPULAR_LANGUAGES],
    }


@router.post("/pipeline/finish", response_model=PipelineFinishStartResponse)
def run_pipeline_finish(body: PipelineFinishRequest):
    """Translate (optional), save Doc + registry Sheet — runs as background job."""
    if not get_credentials():
        raise HTTPException(status_code=401, detail="Connect your Google account first")

    job_id = job_manager.create()
    submit_task(_run_pipeline_finish_job, job_id, body.model_dump())
    return PipelineFinishStartResponse(job_id=job_id)


def _run_pipeline_finish_job(job_id: str, body_data: dict) -> None:
    body = PipelineFinishRequest(**body_data)

    def on_progress(step: str, progress: float) -> None:
        job_manager.update(job_id, status="running", step=step, progress=progress)

    try:
        job_manager.update(job_id, status="running", step="Starting save pipeline", progress=0.02)
        result = _finish_auto_pipeline(
            source=body.source,
            transcript=body.transcript,
            detected_language=body.detected_language,
            duration=body.duration,
            title=body.title,
            upload_filename=body.upload_filename,
            target_languages=body.target_languages or None,
            on_progress=on_progress,
        )
        job_manager.update(
            job_id,
            status="completed",
            step="Done",
            progress=1.0,
            result=result.model_dump(),
        )
    except HTTPException as e:
        job_manager.update(job_id, status="failed", error=str(e.detail))
    except Exception as e:
        job_manager.update(job_id, status="failed", error=str(e))
