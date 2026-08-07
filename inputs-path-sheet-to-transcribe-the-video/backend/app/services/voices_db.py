"""Local voice clone registry (JSON database)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import get_settings


def _voices_path() -> Path:
    settings = get_settings()
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "voices.json"


def _read() -> list[dict]:
    path = _voices_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write(voices: list[dict]) -> None:
    _voices_path().write_text(json.dumps(voices, indent=2), encoding="utf-8")


def list_voices() -> list[dict]:
    return _read()


def get_voice(voice_id: str) -> Optional[dict]:
    for v in _read():
        if v.get("id") == voice_id:
            return v
    return None


def find_by_name(name: str) -> Optional[dict]:
    key = name.strip().lower()
    for v in _read():
        if (v.get("name") or "").strip().lower() == key:
            return v
    return None


def add_voice(
    *,
    name: str,
    provider_voice_id: str,
    sample_filename: Optional[str] = None,
) -> dict:
    existing = find_by_name(name)
    if existing:
        existing["provider_voice_id"] = provider_voice_id
        if sample_filename:
            existing["sample_filename"] = sample_filename
        voices = _read()
        for i, v in enumerate(voices):
            if v.get("id") == existing["id"]:
                voices[i] = existing
                break
        _write(voices)
        return existing

    entry = {
        "id": str(uuid.uuid4()),
        "name": name.strip(),
        "provider_voice_id": provider_voice_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sample_filename": sample_filename,
    }
    voices = _read()
    voices.append(entry)
    _write(voices)
    return entry


def delete_voice(voice_id: str) -> bool:
    voices = _read()
    new = [v for v in voices if v.get("id") != voice_id]
    if len(new) == len(voices):
        return False
    _write(new)
    return True
