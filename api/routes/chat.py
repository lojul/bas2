"""Chat endpoints — streaming SSE + non-streaming fallback."""

import asyncio
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from api.auth import get_current_user

router = APIRouter(prefix="/chat", tags=["chat"])


# ── Request / Response models ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str
    thread_id: str | None = None


class ChatReply(BaseModel):
    answer: str
    sources: list[dict]
    thread_id: str
    error: str | None = None


class ReportRequest(BaseModel):
    sources: list[dict]
    district: str = ""
    district_en: str = ""
    report_type: str = "rent"


class FeedbackRequest(BaseModel):
    thread_id: str
    question: str
    answer: str
    rating: str          # "up" | "down"
    message_index: int | None = None


# ── Lazy import helper (avoids loading heavy ML deps at startup) ─────────────

def _get_chatbot():
    from src.nodes.chatbot import (
        chat,
        chat_stream,
        get_conversation_history,
        clear_conversation,
        get_stream_metadata,
    )
    return chat, chat_stream, get_conversation_history, clear_conversation, get_stream_metadata


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("", response_model=ChatReply)
def send_message(
    body: ChatRequest,
    username: Annotated[str, Depends(get_current_user)],
):
    """Non-streaming chat. Returns full answer + sources."""
    chat, *_ = _get_chatbot()
    thread_id = body.thread_id or str(uuid.uuid4())
    response = chat(body.question, thread_id=thread_id)
    return ChatReply(
        answer=response.answer,
        sources=response.sources,
        thread_id=thread_id,
        error=response.error,
    )


@router.get("/stream")
async def stream_message(
    question: Annotated[str, Query(min_length=1)],
    thread_id: Annotated[str | None, Query()] = None,
    username: Annotated[str, Depends(get_current_user)] = None,
):
    """SSE streaming chat.

    Events:
      data: {"chunk": "..."}        — text token
      data: {"done": true, "sources": [...], "thread_id": "..."}  — final
      data: {"error": "..."}        — on failure
    """
    _, chat_stream, _, _, get_stream_metadata = _get_chatbot()
    tid = thread_id or str(uuid.uuid4())

    async def event_generator():
        loop = asyncio.get_running_loop()

        # Run sync generator in a thread so we don't block the event loop
        gen_iter = chat_stream(question, thread_id=tid)

        try:
            while True:
                chunk = await loop.run_in_executor(None, next, gen_iter, None)
                if chunk is None:
                    break
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        # Final event — includes sources + thread_id so client can store it
        metadata = get_stream_metadata(tid)
        yield f"data: {json.dumps({'done': True, 'sources': metadata.sources, 'thread_id': tid})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/conversations/{thread_id}")
def get_history(
    thread_id: str,
    username: Annotated[str, Depends(get_current_user)],
):
    """Return conversation history for a thread."""
    _, _, get_conversation_history, *_ = _get_chatbot()
    messages = get_conversation_history(thread_id)
    return {"thread_id": thread_id, "messages": messages}


@router.post("/report")
def generate_report(
    body: ReportRequest,
    username: Annotated[str, Depends(get_current_user)],
):
    """Generate a PDF report from chat sources."""
    from src.nodes.report_generator.main import generate_report_from_sources
    result = generate_report_from_sources(
        sources=body.sources,
        district=body.district or "香港",
        district_en=body.district_en or "Hong Kong",
        report_type=body.report_type,
    )
    if result.error:
        raise HTTPException(status_code=400, detail=result.error)
    if not result.report or not result.report.pdf_bytes:
        raise HTTPException(status_code=500, detail="PDF generation failed")
    return Response(
        content=bytes(result.report.pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="property_report.pdf"'},
    )


@router.post("/feedback", status_code=204)
def submit_feedback(
    body: FeedbackRequest,
    username: Annotated[str, Depends(get_current_user)],
):
    """Save a 👍/👎 rating for a chatbot answer."""
    if body.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating must be 'up' or 'down'")
    from src.utils.table_storage import log_feedback
    log_feedback(
        thread_id=body.thread_id,
        question=body.question,
        answer=body.answer,
        rating=body.rating,
        channel="dashboard",
        message_index=body.message_index,
    )


@router.delete("/conversations/{thread_id}")
def clear_history(
    thread_id: str,
    username: Annotated[str, Depends(get_current_user)],
):
    """Clear conversation history for a thread."""
    _, _, _, clear_conversation, _ = _get_chatbot()
    ok = clear_conversation(thread_id)
    return {"thread_id": thread_id, "cleared": ok}
