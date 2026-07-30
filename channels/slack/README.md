# Slack adapter (not yet built)

This will be a thin adapter only: Slack Events API webhook receives a message,
translates it into `POST /api/v1/chat` with `channel="slack"` and
`conversation_id="slack:{channel_id}/{user_id}"`, then posts the reply back to
Slack. No agent/search/Odoo logic lives here — that all lives in `core/`.
