from fastapi import APIRouter, HTTPException

from app.models.schemas import TranslateRequest, TranslateResponse
from app.services.translate import translate_text

router = APIRouter(prefix="/api", tags=["translate"])


@router.post("/translate", response_model=TranslateResponse)
def translate_endpoint(body: TranslateRequest):
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")
    try:
        translated, provider = translate_text(body.text, body.target_language, body.source_language)
        return TranslateResponse(translated_text=translated, provider=provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {e}") from e
