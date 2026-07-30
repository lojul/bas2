# Slack adapter

Thin adapter only — no agent/search/Odoo logic here, that all lives in `core/`
and is reached only via the deployed chatbot API's `POST /api/v1/chat`.

Deployed as its OWN Azure Function App, separate from the core API's App
Service — keeps the channel adapter physically decoupled, same principle as
keeping it a separate code module.

## Why two functions, not one
Slack requires an HTTP ack within 3 seconds of an event, but the actual
chatbot call (LLM + tool calls) can take much longer. So:

- `slack_events` (HTTP trigger) — verifies the request is genuinely from
  Slack (HMAC signature check), answers Slack's one-time URL verification
  challenge, and for a real message enqueues it, then acks immediately.
- `slack_worker` (Queue trigger) — dequeues, calls the core chatbot API,
  posts the reply back to Slack via `chat.postMessage`. Runs on its own time,
  no timeout pressure.

## Required app settings (on the Function App, not in code/git)
- `SLACK_SIGNING_SECRET` — from Slack's Basic Information page
- `SLACK_BOT_TOKEN` — from Slack's OAuth & Permissions page (`xoxb-...`)
- `CHATBOT_API_URL` — the core API's `/api/v1/chat` endpoint
- `CHATBOT_API_KEY` — the `slack:` key from the core API's `CHANNEL_API_KEYS`
- `AzureWebJobsStorage` — set automatically by Azure Functions
