"""Send a Teams message outside a live turn (Bot Framework proactive messaging).

Deliberately does NOT use the botbuilder SDK's own continue_conversation() —
that needs an async adapter instance, and this notifier is called from sync
code (job_queue.py's Function App worker, assistant.py's thread fallback),
same constraint whatsapp_notify.py/slack_notify.py already work under. A
plain OAuth2 client-credentials token + a direct POST to the Bot Connector
REST API is the same mechanism the SDK uses internally, just without the
async wrapper.

Requires MICROSOFT_APP_ID/MICROSOFT_APP_PASSWORD/MICROSOFT_APP_TENANT_ID
(same env vars api/routes/teams.py's inbound auth uses) and a previously
saved ConversationReference (see teams_conversations.py) for the target user.
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_TOKEN_URL_FMT = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_BOT_FRAMEWORK_SCOPE = "https://api.botframework.com/.default"


def _get_token() -> str | None:
    tenant = os.environ.get("MICROSOFT_APP_TENANT_ID", "")
    app_id = os.environ.get("MICROSOFT_APP_ID", "")
    app_password = os.environ.get("MICROSOFT_APP_PASSWORD", "")
    if not (tenant and app_id and app_password):
        return None
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                _TOKEN_URL_FMT.format(tenant=tenant),
                data={
                    "grant_type": "client_credentials",
                    "client_id": app_id,
                    "client_secret": app_password,
                    "scope": _BOT_FRAMEWORK_SCOPE,
                },
            )
            resp.raise_for_status()
            return resp.json().get("access_token")
    except Exception as e:
        logger.warning("Teams token fetch failed: %s", e)
        return None


def send_teams(user_id: str, text: str) -> bool:
    """Send a proactive message to a Teams user, looked up by user_id (the same
    id handle_message() uses — Teams' conversation.id). Returns True on success."""
    from src.utils.teams_conversations import get_conversation_reference

    reference = get_conversation_reference(user_id)
    if not reference:
        logger.warning("No saved Teams conversation reference for %s", user_id)
        return False

    token = _get_token()
    if not token:
        return False

    service_url = reference.get("service_url", "").rstrip("/")
    conversation_id = (reference.get("conversation") or {}).get("id")
    if not (service_url and conversation_id):
        return False

    bot = reference.get("bot") or {}
    user = reference.get("user") or {}

    payload = {
        "type": "message",
        "text": text,
        "from": bot,
        "recipient": user,
        "conversation": {"id": conversation_id},
        "channelId": reference.get("channel_id", "msteams"),
        "serviceUrl": service_url,
    }

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                f"{service_url}/v3/conversations/{conversation_id}/activities",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code >= 300:
                logger.warning("Teams notify failed (%s): %s", resp.status_code, resp.text[:200])
                return False
            return True
    except Exception as e:
        logger.warning("Teams notify error: %s", e)
        return False
