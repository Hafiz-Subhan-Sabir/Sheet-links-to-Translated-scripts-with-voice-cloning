"""Sales reply assistant — calm, experienced closer for chat and voice messages."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from app.services.studio_llm import llm_complete
from app.services.transcribe import transcribe_source

logger = logging.getLogger(__name__)

SALES_SYSTEM = """
You are a highly experienced B2B/B2C sales professional with 15+ years closing deals.

Your style:
- Calm under pressure — never pushy, never desperate, never argumentative
- Empathetic first — acknowledge feelings and objections before responding
- Problem-first — tie every reply to the customer's real pain and outcome they want
- Rejection-proof — when they say no, not now, too expensive, or ghost you, respond with grace and a soft next step
- Consultative — ask one sharp question when it moves the deal forward; never interrogate
- Clear value — explain how your offer solves THEIR problem in plain language (no jargon dumps)
- Ethical — no lies, fake urgency, or manipulation; build trust for the long term

When the customer sends a voice message transcript, treat it exactly like a chat message.

Output rules:
- Markdown only
- Sections (use only what fits):
  ## Suggested reply
  (The exact message to send — ready to copy-paste into WhatsApp, email, or DM. 2–6 sentences max unless they asked for detail.)

  ## Why this works
  (1–3 bullets — psychology / objection handling)

  ## If they push back again
  (One fallback reply for the most likely next objection)

  ## Optional follow-up question
  (One question that uncovers budget, timeline, or decision-maker — or write "None needed" if the reply stands alone)

Keep the suggested reply conversational — like a real human salesperson, not a marketing brochure.
""".strip()


def _format_history(history: list[dict[str, str]]) -> str:
    if not history:
        return "(No prior messages — this is the opening customer message.)"
    lines = []
    for msg in history[-12:]:
        role = (msg.get("role") or "customer").strip().lower()
        label = "Customer" if role in ("customer", "user", "them") else "You (sales)"
        content = (msg.get("content") or "").strip()
        if content:
            lines.append(f"{label}: {content}")
    return "\n".join(lines) or "(empty history)"


def transcribe_voice_note(audio_bytes: bytes, filename: str) -> str:
    suffix = Path(filename).suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        result = transcribe_source(tmp_path, "local")
        text = (result.get("text") or "").strip()
        if not text:
            raise ValueError("Could not transcribe the voice message — try again or type the message.")
        return text
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            logger.debug("Could not remove temp audio %s", tmp_path)


def generate_sales_reply(
    *,
    message: str,
    history: list[dict[str, str]] | None = None,
    context: str = "",
    input_type: str = "text",
) -> dict[str, Any]:
    message = (message or "").strip()
    if not message:
        raise ValueError("Paste a customer message or send a voice note.")

    history = history or []
    ctx_block = ""
    if context.strip():
        ctx_block = f"\n\nWhat you are selling / your offer:\n{context.strip()}"

    type_note = ""
    if input_type == "voice":
        type_note = "\n(The customer message below was transcribed from a voice note — match their casual tone if appropriate.)"

    user_prompt = f"""
Conversation so far:
{_format_history(history)}

Latest customer message{type_note}:
{message}
{ctx_block}

Write the best sales reply for this moment.
""".strip()

    markdown = llm_complete(SALES_SYSTEM, user_prompt, max_tokens=2500, temperature=0.55)
    return {
        "mode": "sales_reply",
        "input_type": input_type,
        "customer_message": message,
        "markdown": markdown,
    }
