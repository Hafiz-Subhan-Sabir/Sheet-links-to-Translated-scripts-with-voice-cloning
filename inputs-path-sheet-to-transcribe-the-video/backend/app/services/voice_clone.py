"""Fish Audio voice cloning + TTS synthesis (s2.1-pro-free by default)."""

from __future__ import annotations

import logging
import mimetypes
import re
from pathlib import Path
from typing import Optional

import httpx

from app.config import get_settings
from app.services import voices_db

logger = logging.getLogger(__name__)

FISH_API_BASE = "https://api.fish.audio"


class VoiceCloneError(Exception):
    pass


def fish_configured() -> bool:
    return bool(get_settings().fish_api_key.strip())


# Kept for older call sites / API field name compatibility
def elevenlabs_configured() -> bool:
    return fish_configured()


def resolve_voice_output_dir(override: Optional[str] = None) -> Path:
    from app.services.storage import storage

    if override and override.strip():
        path = Path(override.strip())
    else:
        cfg = storage.get_admin_config().get("voice_output_dir")
        settings = get_settings()
        path = Path(cfg.strip()) if cfg and str(cfg).strip() else Path(settings.voice_output_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _auth_headers(api_key: str, *, json_body: bool = False, model: Optional[str] = None) -> dict:
    h = {"Authorization": f"Bearer {api_key}"}
    if json_body:
        h["Content-Type"] = "application/json"
    if model:
        h["model"] = model
    return h


def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "application/octet-stream"


def create_cloned_voice(
    *,
    name: str,
    sample_path: str,
    description: str = "Cloned via Transcript Studio",
) -> dict:
    """
    Upload a sample to Fish Audio Instant Voice Cloning (POST /model).
    Returns local voices_db entry with Fish model id as provider_voice_id.
    """
    settings = get_settings()
    api_key = settings.fish_api_key.strip()
    if not api_key:
        raise VoiceCloneError("FISH_API_KEY is not set in backend .env")

    path = Path(sample_path)
    if not path.is_file():
        raise VoiceCloneError(f"Sample file not found: {sample_path}")

    existing = voices_db.find_by_name(name)
    if existing and existing.get("provider_voice_id"):
        return existing

    with open(path, "rb") as f:
        files = {"voices": (path.name, f, _guess_mime(path))}
        data = {
            "type": "tts",
            "title": name.strip(),
            "description": description,
            "visibility": "private",
            "train_mode": "fast",
            "enhance_audio_quality": "true",
        }
        with httpx.Client(timeout=180.0) as client:
            resp = client.post(
                f"{FISH_API_BASE}/model",
                headers=_auth_headers(api_key),
                data=data,
                files=files,
            )
            if resp.status_code >= 400:
                raise VoiceCloneError(
                    f"Fish Audio voice clone failed ({resp.status_code}): {resp.text[:500]}"
                )
            payload = resp.json()

    provider_id = payload.get("_id") or payload.get("id")
    if not provider_id:
        raise VoiceCloneError(f"Fish Audio response missing model id: {payload}")

    return voices_db.add_voice(
        name=name.strip(),
        provider_voice_id=str(provider_id),
        sample_filename=path.name,
    )


def synthesize_to_file(
    *,
    provider_voice_id: str,
    text: str,
    output_path: Path,
) -> Path:
    settings = get_settings()
    api_key = settings.fish_api_key.strip()
    if not api_key:
        raise VoiceCloneError("FISH_API_KEY is not set")

    clean = (text or "").strip()
    if not clean:
        raise VoiceCloneError("Empty text — nothing to synthesize")

    # Fish handles longer text; still chunk for reliability on huge transcripts
    chunks = _chunk_for_tts(clean, max_chars=4000)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    model = (settings.fish_model or "s2.1-pro-free").strip()

    audio_parts: list[bytes] = []
    with httpx.Client(timeout=300.0) as client:
        for chunk in chunks:
            resp = client.post(
                f"{FISH_API_BASE}/v1/tts",
                headers=_auth_headers(api_key, json_body=True, model=model),
                json={
                    "text": chunk,
                    "reference_id": provider_voice_id,
                    "format": "mp3",
                    "normalize": True,
                    "latency": "normal",
                    "mp3_bitrate": 192,
                },
            )
            if resp.status_code >= 400:
                raise VoiceCloneError(
                    f"Fish Audio TTS failed ({resp.status_code}): {resp.text[:500]}"
                )
            audio_parts.append(resp.content)

    output_path.write_bytes(b"".join(audio_parts))
    return output_path


def _chunk_for_tts(text: str, max_chars: int = 4000) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            split = text.rfind("\n", start, end)
            if split <= start + max_chars // 3:
                split = text.rfind(". ", start, end)
            if split > start:
                end = split + 1
        chunks.append(text[start:end].strip())
        start = end
    return [c for c in chunks if c]


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^\w\s\-\.]", "", name, flags=re.UNICODE).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return (cleaned or "audio")[:120]
