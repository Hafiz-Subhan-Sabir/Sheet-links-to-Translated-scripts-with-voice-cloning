import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import get_settings


@dataclass
class Job:
    job_id: str
    status: str = "pending"
    step: str = "Validating input"
    progress: float = 0.0
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class JobManager:
    def __init__(self) -> None:
        settings = get_settings()
        self._path = Path(settings.data_dir) / "jobs.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, Job] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            for job_id, data in raw.items():
                self._jobs[job_id] = Job(**data)
        except Exception:
            self._jobs = {}
        self._recover_interrupted_jobs()

    def _recover_interrupted_jobs(self) -> None:
        """Jobs left running when the server restarts cannot continue."""
        changed = False
        for job in self._jobs.values():
            if job.status in ("pending", "running"):
                job.status = "failed"
                job.error = "Interrupted by server restart. Click the video again to transcribe."
                changed = True
        if changed:
            self._save()

    def _save(self) -> None:
        data = {job_id: asdict(job) for job_id, job in self._jobs.items()}
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def create(self) -> str:
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = Job(job_id=job_id)
        self._save()
        return job_id

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def update(
        self,
        job_id: str,
        *,
        status: Optional[str] = None,
        step: Optional[str] = None,
        progress: Optional[float] = None,
        result: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        if status is not None:
            job.status = status
        if step is not None:
            job.step = step
        if progress is not None:
            job.progress = progress
        if result is not None:
            job.result = result
        if error is not None:
            job.error = error
        self._save()

    def to_response(self, job_id: str, *, include_result: bool = True) -> dict[str, Any]:
        job = self._jobs[job_id]
        result = job.result if include_result and job.status == "completed" else None
        return {
            "job_id": job.job_id,
            "status": job.status,
            "step": job.step,
            "progress": job.progress,
            "result": result,
            "error": job.error,
        }


job_manager = JobManager()
