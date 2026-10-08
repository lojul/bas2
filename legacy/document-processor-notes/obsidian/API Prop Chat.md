# API Prop Chat

**File:** `langgraph/api/prop_chat_main.py`
**URL:** `https://c21net-bas-api-prop-chat-ea-prod.azurewebsites.net`

## Routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Health check |
| POST | `/api/chat/stream` | SSE streaming chat (dashboard) |
| POST | `/api/chat/report` | Generate PDF report from chat sources |
| POST | `/api/search` | Keyword/hybrid/vector search |

## Deploy

```bash
cd langgraph && ./deploy.sh --chat
```

## Connects to

[[Search]] — powers /api/search and chat retrieval
[[API Doc Pipeline]] — same codebase zip, different startup command
