"""Shared thread pool for background transcription and prefetch work."""
from concurrent.futures import ThreadPoolExecutor

from app.config import get_settings

_executor: ThreadPoolExecutor | None = None


def get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        settings = get_settings()
        _executor = ThreadPoolExecutor(
            max_workers=max(2, settings.worker_threads),
            thread_name_prefix="vts-worker",
        )
    return _executor


def submit_task(fn, *args, **kwargs):
    return get_executor().submit(fn, *args, **kwargs)
