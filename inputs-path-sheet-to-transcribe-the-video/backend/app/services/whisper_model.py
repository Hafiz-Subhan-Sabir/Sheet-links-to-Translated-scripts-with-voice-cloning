"""Cached faster-whisper model — load once, reuse across jobs for faster startup."""
from __future__ import annotations

import os
import threading
from typing import Optional

from app.config import get_settings

_model = None
_model_key: Optional[tuple] = None
_lock = threading.Lock()
_ready = threading.Event()


def _resolve_cpu_threads() -> int:
    settings = get_settings()
    if settings.whisper_cpu_threads > 0:
        return settings.whisper_cpu_threads
    cores = os.cpu_count() or 4
    return max(2, cores - 1)


def _resolve_num_workers() -> int:
    settings = get_settings()
    if settings.whisper_num_workers > 0:
        return settings.whisper_num_workers
    cores = os.cpu_count() or 4
    return max(2, min(4, cores // 2))


def _model_cache_key() -> tuple:
    settings = get_settings()
    return (settings.whisper_model, _resolve_cpu_threads(), _resolve_num_workers())


def is_whisper_ready() -> bool:
    return _ready.is_set()


def preload_whisper_model() -> None:
    """Load Whisper into memory (background-safe)."""
    global _model, _model_key
    from faster_whisper import WhisperModel

    key = _model_cache_key()
    with _lock:
        if _model is not None and _model_key == key:
            _ready.set()
            return

        settings = get_settings()
        cpu_threads = key[1]
        num_workers = key[2]
        _model = WhisperModel(
            settings.whisper_model,
            device="cpu",
            compute_type="int8",
            cpu_threads=cpu_threads,
            num_workers=num_workers,
        )
        _model_key = key
        _ready.set()


def get_whisper_model():
    """Return cached model, loading on first use."""
    if _model is None or _model_key != _model_cache_key():
        preload_whisper_model()
    return _model
