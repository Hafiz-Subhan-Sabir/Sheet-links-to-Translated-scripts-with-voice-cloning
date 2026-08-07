from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import admin, auth, batch, detect, transcribe, voice
from app.services.transcribe import schedule_whisper_preload
from app.services.workers import submit_task


@asynccontextmanager
async def lifespan(app: FastAPI):
    submit_task(schedule_whisper_preload)
    yield


app = FastAPI(
    title="Sheet → Transcript → Translate → Voice Clone",
    description=(
        "Batch transcribe videos from an input Google Sheet, translate into "
        "English variants + top languages, write an output sheet + Google Docs, "
        "then optionally voice-clone selected transcripts."
    ),
    version="2.0.0",
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
app.include_router(detect.router)
app.include_router(transcribe.router)
app.include_router(auth.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"status": "ok"}
