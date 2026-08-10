from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    admin_password: str = "changeme"
    secret_key: str = "dev-secret-key-change-in-production"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"
    openai_api_key: str = ""
    google_translate_api_key: str = ""
    google_translate_mode: str = "auto"
    whisper_model: str = "medium"
    whisper_engine: str = "auto"  # auto | openai | local
    whisper_cpu_threads: int = 0
    whisper_num_workers: int = 0
    translate_workers: int = 8
    google_docs_batch_requests: int = 40
    google_docs_chunk_chars: int = 80_000
    google_upload_workers: int = 4
    upload_chunk_size: int = 8 * 1024 * 1024
    ffmpeg_location: str = ""
    frontend_url: str = "http://localhost:3000"
    data_dir: str = "./data"
    admin_session_minutes: int = 15
    max_unlock_attempts: int = 5
    worker_threads: int = 4
    prefetch_enabled: bool = True
    input_sheet_url: str = ""
    output_sheet_url: str = ""
    openai_model: str = "gpt-4o-mini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    description_provider: str = "off"  # off | auto | openai | gemini — off = no LLM descriptions/category
    description_transcript_max_chars: int = 120_000
    batch_workers: int = 3
    input_sheet_tab: str = ""
    output_sheet_tab: str = ""
    # Fish Audio voice cloning (preferred)
    fish_api_key: str = ""
    fish_model: str = "s2.1-pro-free"
    voice_output_dir: str = "./data/voices_output"
    # Deprecated — kept so old .env files don't break
    elevenlabs_api_key: str = ""
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    # Deprecated — kept so old .env files don't break
    output_doc_title: str = "Video Transcripts"


@lru_cache
def get_settings() -> Settings:
    return Settings()
