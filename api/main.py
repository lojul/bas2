"""Channel-agnostic chat API. The ONLY surface any channel adapter talks to.

No channel-specific logic lives here — Slack, WhatsApp, a web widget, etc. all
call this same contract. See api/auth.py for per-channel API keys.
"""

from datetime import datetime, timezone

from fastapi import FastAPI, Header
from pydantic import BaseModel

from api.auth import verify_channel_key
from core.agent import run_turn

app = FastAPI(title="C21 Property Chatbot API")


class ChatRequest(BaseModel):
    channel: str
    conversation_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    sources: list[dict]
    conversation_id: str


@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(req: ChatRequest, x_api_key: str = Header(default="")) -> ChatResponse:
    verify_channel_key(req.channel, x_api_key)
    result = run_turn(req.channel, req.conversation_id, req.message)
    return ChatResponse(**result)


@app.delete("/api/v1/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict:
    # TODO: clear checkpointer state for this conversation_id once agent.py is real
    return {"status": "not yet implemented"}


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}
