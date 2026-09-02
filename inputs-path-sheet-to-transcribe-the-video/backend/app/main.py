from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import admin, auth, batch, detect, edit, prospect, sales, studio, transcribe, voice
from app.services.transcribe import schedule_whisper_preload
from app.services.workers import submit_task


def _bootstrap_media_bins() -> None:
    from app.services.media_bins import ensure_media_bins

    try:
        ensure_media_bins()
    except Exception as e:
        # Non-fatal at startup — first download/transcribe will retry
        import logging

        logging.getLogger(__name__).warning("Media bin bootstrap deferred: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    submit_task(_bootstrap_media_bins)
    submit_task(schedule_whisper_preload)
    yield


app = FastAPI(
    title="Sheet → Transcript → Translate → Voice Clone",
    description=(
        "Batch transcribe videos from an input Google Sheet, translate into "
        "English variants + top languages, write an output sheet + Google Docs, "
        "then optionally voice-clone selected transcripts. Also includes Studio "
        "modes for original scripts and viral/Shorts analysis, plus auto visual "
        "edit packs (timed AI stills, rough MP4, CapCut import guide)."
    ),
    version="2.2.0",
    lifespan=lifespan,
)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(batch.router)
app.include_router(voice.router)
app.include_router(studio.router)
app.include_router(sales.router)
app.include_router(prospect.router)
app.include_router(edit.router)
app.include_router(detect.router)
app.include_router(transcribe.router)
app.include_router(auth.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"status": "ok"}
