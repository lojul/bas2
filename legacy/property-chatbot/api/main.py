"""Channel-agnostic chat API. The ONLY surface any channel adapter talks to.

No channel-specific logic lives here — Slack, WhatsApp, a web widget, etc. all
call this same contract. See api/auth.py for per-channel API keys.

Run locally: python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
Same startup command used on Azure App Service (see deploy notes).
"""

from datetime import datetime, timezone

from fastapi import FastAPI, Header
from pydantic import BaseModel

from api.auth import verify_channel_key
from core.agent import run_turn
from core.rate_limit import check_and_increment, get_usage

app = FastAPI(title="C21 Property Chatbot API")

# Deterministic status check — no LLM call, doesn't count against the quota.
# Channel-agnostic on purpose (same as everything else here): matches on
# message content, not on which channel it came from.
_USAGE_QUERY_KEYWORDS = (
    "usage", "quota", "how many message", "messages left", "message limit",
    "幾多次", "剩幾多", "額度", "配額",
)


def _is_usage_query(message: str) -> bool:
    lowered = message.lower()
    return any(k in lowered for k in _USAGE_QUERY_KEYWORDS)


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

    if _is_usage_query(req.message):
        used, limit = get_usage(req.conversation_id)
        return ChatResponse(
            reply=f"You've used {used}/{limit} messages today. Resets at 00:00 UTC.",
            sources=[],
            conversation_id=req.conversation_id,
        )

    allowed, used, limit = check_and_increment(req.conversation_id)
    if not allowed:
        return ChatResponse(
            reply=f"You've reached today's limit ({limit} messages per day). Please try again after 00:00 UTC.",
            sources=[],
            conversation_id=req.conversation_id,
        )

    result = run_turn(req.channel, req.conversation_id, req.message)
    return ChatResponse(**result)


@app.delete("/api/v1/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict:
    # TODO: clear checkpointer state for this conversation_id once agent.py is real
    return {"status": "not yet implemented"}


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}
