"""Send WhatsApp messages via the n8n notify webhook.

n8n is integration-only: it holds the Twilio credentials and forwards
{to, body} to the Twilio API. Auth: X-Api-Key = ASSISTANT_API_KEY.
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)


def send_whatsapp(to: str, body: str) -> bool:
    """Send a WhatsApp message to a user. Returns True on success."""
    url = os.environ.get("N8N_NOTIFY_WEBHOOK_URL", "")
    api_key = os.environ.get("ASSISTANT_API_KEY", "")
    if not url or not to or not body:
        return False
    if not to.startswith("whatsapp:"):
        to = f"whatsapp:{to}"
    # Twilio enforces a 1600-char limit on outgoing messages (Error 21617).
    # Emoji and CJK characters count as multiple chars, so truncate conservatively.
    body = body[:1400] + ("…" if len(body) > 1400 else "")
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                url,
                json={"to": to, "body": body},
                headers={"X-Api-Key": api_key},
            )
            if resp.status_code >= 300:
                logger.warning("WhatsApp notify failed (%s): %s", resp.status_code, resp.text[:200])
                return False
            return True
    except Exception as e:
        logger.warning("WhatsApp notify error: %s", e)
        return False
