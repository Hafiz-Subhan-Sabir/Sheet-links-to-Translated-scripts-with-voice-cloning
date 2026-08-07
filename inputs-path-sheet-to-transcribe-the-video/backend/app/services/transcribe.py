import re
import threading
import time
from typing import Callable, Optional

from app.config import get_settings
from app.models.schemas import TranscriptSegment
from app.services.video import VideoError, download_audio_from_url, prepare_local_audio
from app.services.whisper_model import (
    _resolve_cpu_threads,
    _resolve_num_workers,
    get_whisper_model,
    is_whisper_ready,
    preload_whisper_model,
)

# Progress bands: setup 0–12%, transcription 12–97%, finalize 99%
_PROGRESS_SETUP_END = 0.12
_PROGRESS_TRANSCRIBE_SPAN = 0.85


def schedule_whisper_preload() -> None:
    """Warm Whisper model in a background thread."""
    preload_whisper_model()


def _format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"[{h:02d}:{m:02d}:{s:02d}]"
    return f"[{m:02d}:{s:02d}]"


def _cleanup_punctuation(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


def _add_paragraph_breaks(segments: list[dict], gap_threshold: float = 1.5) -> str:
    lines: list[str] = []
    prev_end = 0.0
    for seg in segments:
        if prev_end > 0 and seg["start"] - prev_end > gap_threshold and lines:
            lines.append("")
        ts = _format_timestamp(seg["start"])
        lines.append(f"{ts} {seg['text']}")
        prev_end = seg["end"]
    return "\n".join(lines)


def _format_progress_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _transcribe_faster_whisper(
    audio_path: str,
    language: Optional[str],
    on_progress: Optional[Callable[[str, float], None]] = None,
    duration_hint: float = 0.0,
) -> dict:
    settings = get_settings()
    cpu_threads = _resolve_cpu_threads()
    num_workers = _resolve_num_workers()

    if on_progress:
        if is_whisper_ready():
            on_progress(
                f"Whisper ready ({settings.whisper_model}, {cpu_threads} threads × {num_workers} workers)",
                0.10,
            )
        else:
            on_progress(
                f"Loading Whisper model ({settings.whisper_model}, {cpu_threads} threads × {num_workers} workers)…",
                0.05,
            )

    model = get_whisper_model()

    if on_progress:
        on_progress(
            f"Transcribing with {cpu_threads} CPU threads, {num_workers} parallel workers…",
            0.11,
        )

    segments_iter, info = model.transcribe(
        audio_path,
        language=None if not language or language == "auto" else language,
        vad_filter=True,
        word_timestamps=True,
        beam_size=1,
    )

    total_duration = float(duration_hint or info.duration or 0)
    if total_duration <= 0:
        total_duration = float(info.duration or 0)

    max_end_seen = 0.0
    if on_progress:
        if total_duration > 0:
            on_progress(
                f"Transcribing 0:00 / {_format_progress_time(total_duration)}",
                _PROGRESS_SETUP_END,
            )
        else:
            on_progress("Transcribing audio…", _PROGRESS_SETUP_END)
    segments: list[dict] = []
    confidences: list[float] = []
    for seg in segments_iter:
        text = _cleanup_punctuation(seg.text.strip())
        if not text:
            continue
        avg_prob = None
        if seg.words:
            probs = [w.probability for w in seg.words if w.probability is not None]
            if probs:
                avg_prob = sum(probs) / len(probs)
                confidences.append(avg_prob)
        segments.append(
            {
                "start": seg.start,
                "end": seg.end,
                "text": text,
                "confidence": avg_prob,
            }
        )
        if on_progress and total_duration > 0:
            max_end_seen = max(max_end_seen, float(seg.end))
            ratio = min(1.0, max_end_seen / total_duration)
            pct = _PROGRESS_SETUP_END + ratio * _PROGRESS_TRANSCRIBE_SPAN
            on_progress(
                f"Transcribing {_format_progress_time(max_end_seen)} / {_format_progress_time(total_duration)}",
                pct,
            )

    transcript = _add_paragraph_breaks(segments)
    avg_confidence = sum(confidences) / len(confidences) if confidences else None

    return {
        "transcript": transcript,
        "segments": segments,
        "language": info.language or "unknown",
        "duration": info.duration or 0.0,
        "confidence": avg_confidence,
    }


def _transcribe_openai(
    audio_path: str,
    language: Optional[str],
    on_progress: Optional[Callable[[str, float], None]] = None,
) -> dict:
    from openai import OpenAI

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key, timeout=600.0)

    if on_progress:
        on_progress("Uploading audio to OpenAI Whisper…", 0.15)

    stop_heartbeat = threading.Event()

    def _heartbeat() -> None:
        pct = 0.25
        while not stop_heartbeat.wait(6):
            pct = min(0.48, pct + 0.02)
            if on_progress:
                on_progress("Still transcribing with OpenAI Whisper (cloud)…", pct)

    heartbeat = threading.Thread(target=_heartbeat, daemon=True)
    heartbeat.start()

    try:
        with open(audio_path, "rb") as f:
            if on_progress:
                on_progress("Transcribing with OpenAI Whisper (cloud)…", 0.25)
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language=None if not language or language == "auto" else language,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )
    finally:
        stop_heartbeat.set()
        heartbeat.join(timeout=1)

    segments: list[dict] = []
    for seg in response.segments or []:
        text = _cleanup_punctuation(seg.text.strip())
        if text:
            segments.append({"start": seg.start, "end": seg.end, "text": text, "confidence": None})

    return {
        "transcript": _add_paragraph_breaks(segments) if segments else response.text,
        "segments": segments,
        "language": response.language or "unknown",
        "duration": response.duration or 0.0,
        "confidence": None,
    }


def transcribe_source(
    source: str,
    source_type: str,
    language: Optional[str] = None,
    upload_path: Optional[str] = None,
    on_progress: Optional[Callable[[str, float], None]] = None,
    *,
    prepared_audio_path: Optional[str] = None,
    prepared_duration: Optional[float] = None,
) -> dict:
    if prepared_audio_path:
        audio_path = prepared_audio_path
        duration_hint = prepared_duration or 0.0
        if on_progress:
            on_progress("Using prepared audio", 0.02)
    elif upload_path:
        if on_progress:
            on_progress("Preparing local audio", 0.01)
        audio_path, duration_hint = prepare_local_audio(upload_path)
    elif source_type == "online":
        if on_progress:
            on_progress("Downloading/preparing audio", 0.01)
        audio_path, duration_hint = download_audio_from_url(source)
    else:
        if on_progress:
            on_progress("Extracting audio from video…", 0.02)
        audio_path, duration_hint = prepare_local_audio(source)

    if on_progress:
        on_progress("Starting transcription engine", 0.03)

    settings = get_settings()
    engine = settings.whisper_engine.lower()
    has_openai = bool(settings.openai_api_key.strip())
    # Local files: prefer on-device Whisper for live progress. Online URLs: prefer OpenAI when available.
    prefer_openai = engine == "openai" or (
        engine == "auto" and has_openai and source_type == "online"
    )
    prefer_local = engine == "local" or (engine == "auto" and source_type == "local")

    if prefer_openai and not prefer_local:
        try:
            result = _transcribe_openai(audio_path, language, on_progress)
        except Exception as e:
            if engine == "openai":
                raise VideoError(f"OpenAI transcription failed: {e}") from e
            if on_progress:
                on_progress("Retrying with local Whisper model", 0.04)
            result = _transcribe_faster_whisper(
                audio_path, language, on_progress, duration_hint=duration_hint
            )
    else:
        try:
            result = _transcribe_faster_whisper(
                audio_path, language, on_progress, duration_hint=duration_hint
            )
        except Exception as e:
            if has_openai and engine == "auto":
                if on_progress:
                    on_progress("Retrying with OpenAI Whisper", 0.08)
                result = _transcribe_openai(audio_path, language, on_progress)
            else:
                raise VideoError(f"Transcription failed: {e}") from e

    if on_progress:
        on_progress("Finalizing transcript", 0.99)

    if duration_hint and not result.get("duration"):
        result["duration"] = duration_hint

    result["segments"] = [
        TranscriptSegment(**s).model_dump() for s in result["segments"]
    ]
    return result
