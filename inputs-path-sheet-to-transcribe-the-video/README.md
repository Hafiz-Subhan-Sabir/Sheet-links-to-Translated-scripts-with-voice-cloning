# Sheet → Translated Scripts + Voice Cloning

Batch tool that reads video links from an **input Google Sheet**, transcribes each video (local path or online URL), translates into British/American English plus the **top 10 languages**, classifies category, writes a rich **output Google Sheet**, creates a **Google Doc per video**, then optionally **voice-clones** selected transcripts with ElevenLabs.

## Monorepo

```
inputs-path-sheet-to-transcribe-the-video/
├── frontend/          # Next.js 14
├── backend/           # FastAPI
├── README.md
└── .env.example
```

## Prerequisites

- Node.js 18+, Python 3.11+, ffmpeg, yt-dlp (via pip)
- Google Cloud project with Docs, Drive, Sheets APIs
- Optional: `OPENAI_API_KEY` / `GEMINI_API_KEY` (category + EN variants)
- Voice cloning: `ELEVENLABS_API_KEY`

## Quick start

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy ..\.env.example .env
# Edit .env: GOOGLE_*, INPUT_SHEET_URL, OUTPUT_SHEET_URL, ELEVENLABS_API_KEY
uvicorn app.main:app --reload --port 8000
```

### Frontend

```powershell
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

Open http://localhost:3000

## Workflow

1. **Input sheet** — video links (local or online)
2. **Process** — transcribe → English + British/American → top 10 languages → category → length → Google Doc → **output sheet**
3. **Voice cloning or mark done**
   - Upload/record a voice sample → clone → saved in local voice DB
   - Select voice from dropdown (or create new)
   - Select transcript rows + language column
   - Synthesize to a chosen directory
   - Output sheet gets Voice Name, Voice Directory, Voice Notes

## Input Google Sheet

| Video Name | Video Path | Status | Error |
|------------|------------|--------|-------|
| Ep 1 | C:\Videos\ep1.mp4 | pending | |
| Ep 2 | https://youtube.com/watch?v=xxx | pending | |

Aliases accepted: `Program Title` / `Title` for name; `Path` / `URL` / `Link` for path.

## Output Google Sheet columns

Video Name · Source Video · English Transcript · British English · American English · Spanish · Chinese (Simplified) · Hindi · Arabic · Portuguese · French · Russian · Japanese · German · Korean · Category · Video Length · Date Transcribed · Detected Language · Google Docs Link · Status · Voice Name · Voice Directory · Voice Notes · Error

Status after batch: `ready_for_voice` → then `voice_cloned` or `marked_done`.

Long cells are truncated at ~49k chars; full text is in the Google Doc.

## Env variables

| Variable | Description |
|----------|-------------|
| `INPUT_SHEET_URL` | Queue of videos |
| `OUTPUT_SHEET_URL` | Results sheet (different spreadsheet) |
| `ELEVENLABS_API_KEY` | Voice cloning |
| `ELEVENLABS_MODEL_ID` | Default `eleven_multilingual_v2` |
| `VOICE_OUTPUT_DIR` | Default folder for cloned MP3s |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` | Category + British/American styling |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | OAuth |
| `BATCH_WORKERS` | Parallel row workers (1–8) |
| `WHISPER_MODEL` | e.g. `medium` |

## API (main)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/batch/config` | Sheet + voice config |
| GET | `/api/batch/queue` | Input rows |
| GET | `/api/batch/output` | Output rows |
| POST | `/api/batch/run` | Process pending |
| POST | `/api/batch/mark-done` | Skip voice cloning |
| GET | `/api/voice/list` | Saved voices DB |
| POST | `/api/voice/clone` | Clone from sample (multipart) |
| POST | `/api/voice/synthesize` | TTS selected rows |
| POST | `/api/voice/output-dir` | Set save directory |

Voices are stored in `backend/data/voices.json`.
