"""Sales reply API — text or voice customer messages."""

from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.services.sales import generate_first_message, generate_sales_reply, transcribe_voice_note
from app.services.studio_llm import StudioLLMError

router = APIRouter(prefix="/api/sales", tags=["sales"])


class ChatMessage(BaseModel):
    role: str = "customer"
    content: str


class SalesReplyRequest(BaseModel):
    message: str = ""
    history: list[ChatMessage] = Field(default_factory=list)
    context: str = ""


class FirstMessageRequest(BaseModel):
    contact_name: str = ""
    contact_phone: str = ""
    contact_email: str = ""
    company: str = ""
    role: str = ""
    notes: str = ""
    offer: str = ""
    channel: str = "whatsapp"


@router.post("/reply")
def sales_reply_json(body: SalesReplyRequest):
    try:
        return generate_sales_reply(
            message=body.message,
            history=[m.model_dump() for m in body.history],
            context=body.context,
            input_type="text",
        )
    except (ValueError, StudioLLMError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/first-message")
def sales_first_message(body: FirstMessageRequest):
    try:
        return generate_first_message(
            contact_name=body.contact_name,
            contact_phone=body.contact_phone,
            contact_email=body.contact_email,
            company=body.company,
            role=body.role,
            notes=body.notes,
            offer=body.offer,
            channel=body.channel,
        )
    except (ValueError, StudioLLMError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/reply-voice")
async def sales_reply_voice(
    voice_note: UploadFile = File(...),
    history_json: str = Form("[]"),
    context: str = Form(""),
):
    try:
        raw = await voice_note.read()
        if not raw:
            raise ValueError("Voice note is empty.")
        filename = voice_note.filename or "voice.webm"
        message = transcribe_voice_note(raw, filename)
        try:
            history = json.loads(history_json or "[]")
            if not isinstance(history, list):
                history = []
        except json.JSONDecodeError:
            history = []
        result = generate_sales_reply(
            message=message,
            history=history,
            context=context,
            input_type="voice",
        )
        result["transcript"] = message
        return result
    except (ValueError, StudioLLMError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
