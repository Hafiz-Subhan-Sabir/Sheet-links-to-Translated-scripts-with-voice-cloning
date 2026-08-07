"""Background audio download cache — starts when user pastes a video URL."""
from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from typing import Literal, Optional

from app.services.video import VideoError, download_audio_from_url

PrefetchStatus = Literal["idle", "pending", "downloading", "ready", "failed"]

_TTL_SECONDS = 2 * 60 * 60  # 2 hours


@dataclass
class PrefetchEntry:
    cache_id: str
    url: str
    status: PrefetchStatus = "pending"
    audio_path: Optional[str] = None
    duration: float = 0.0
    error: Optional[str] = None
    progress: float = 0.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class PrefetchManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_id: dict[str, PrefetchEntry] = {}
        self._url_to_id: dict[str, str] = {}
        self._running: set[str] = set()

    def _normalize_key(self, url: str) -> str:
        return url.strip().lower()

    def _make_cache_id(self, url: str) -> str:
        digest = hashlib.sha256(self._normalize_key(url).encode()).hexdigest()[:16]
        return f"pf_{digest}"

    def _evict_stale(self) -> None:
        now = time.time()
        stale_ids = [
            cid
            for cid, entry in self._by_id.items()
            if now - entry.updated_at > _TTL_SECONDS and entry.status != "downloading"
        ]
        for cid in stale_ids:
            entry = self._by_id.pop(cid, None)
            if entry:
                self._url_to_id.pop(self._normalize_key(entry.url), None)

    def start(self, url: str) -> PrefetchEntry:
        key = self._normalize_key(url)
        with self._lock:
            self._evict_stale()
            existing_id = self._url_to_id.get(key)
            if existing_id and existing_id in self._by_id:
                entry = self._by_id[existing_id]
                entry.updated_at = time.time()
                return entry

            cache_id = self._make_cache_id(url)
            entry = PrefetchEntry(cache_id=cache_id, url=url.strip())
            self._by_id[cache_id] = entry
            self._url_to_id[key] = cache_id
            return entry

    def get(self, cache_id: str) -> Optional[PrefetchEntry]:
        with self._lock:
            entry = self._by_id.get(cache_id)
            if entry:
                entry.updated_at = time.time()
            return entry

    def update(
        self,
        cache_id: str,
        *,
        status: Optional[PrefetchStatus] = None,
        audio_path: Optional[str] = None,
        duration: Optional[float] = None,
        error: Optional[str] = None,
        progress: Optional[float] = None,
    ) -> None:
        with self._lock:
            entry = self._by_id.get(cache_id)
            if not entry:
                return
            if status is not None:
                entry.status = status
            if audio_path is not None:
                entry.audio_path = audio_path
            if duration is not None:
                entry.duration = duration
            if error is not None:
                entry.error = error
            if progress is not None:
                entry.progress = progress
            entry.updated_at = time.time()

    def to_dict(self, entry: PrefetchEntry) -> dict:
        return {
            "cache_id": entry.cache_id,
            "url": entry.url,
            "status": entry.status,
            "duration": entry.duration,
            "progress": entry.progress,
            "error": entry.error,
            "ready": entry.status == "ready" and bool(entry.audio_path),
        }


prefetch_manager = PrefetchManager()


def schedule_prefetch(url: str) -> PrefetchEntry:
    from app.services.workers import submit_task

    entry = prefetch_manager.start(url)
    if entry.status in ("ready", "downloading"):
        return entry

    with prefetch_manager._lock:
        if entry.cache_id in prefetch_manager._running:
            return entry
        prefetch_manager._running.add(entry.cache_id)

    prefetch_manager.update(entry.cache_id, status="downloading", progress=0.05)
    submit_task(_run_prefetch, entry.cache_id, url)
    return entry


def _run_prefetch(cache_id: str, url: str) -> None:
    try:
        prefetch_manager.update(cache_id, status="downloading", progress=0.1)
        audio_path, duration = download_audio_from_url(url)
        prefetch_manager.update(
            cache_id,
            status="ready",
            audio_path=audio_path,
            duration=duration,
            progress=1.0,
            error=None,
        )
    except VideoError as e:
        prefetch_manager.update(cache_id, status="failed", error=str(e), progress=0.0)
    except Exception as e:
        prefetch_manager.update(
            cache_id, status="failed", error=f"Prefetch failed: {e}", progress=0.0
        )
    finally:
        with prefetch_manager._lock:
            prefetch_manager._running.discard(cache_id)
