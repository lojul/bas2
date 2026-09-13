"""Microsoft Teams route — Bot Framework messaging endpoint for document ingest.

Mirrors WhatsApp/Slack: every inbound Teams activity is turned into exactly
one call to the same channel-agnostic src.nodes.assistant.handle_message(),
channel="teams". No ingest logic lives here — this file's only job is Bot
Framework plumbing (auth, activity parsing, attachment resolution, proactive-
messaging bookkeeping) and calling into the shared core, same division of
labor api/routes/assistant.py already has for the other channels.

Auth (validating requests really come from the Bot Connector service, not
just anyone who finds this URL) is handled by CloudAdapter/
ConfigurationBotFrameworkAuthentication using MICROSOFT_APP_ID/
MICROSOFT_APP_PASSWORD/MICROSOFT_APP_TENANT_ID — no custom verification code,
same as bas-stacks' teams-agent (a separate, unrelated bot — see this repo's
CLAUDE.md for why the two must not share an app registration).

Proactive messaging: the pipeline takes 1-3 minutes, so the completion reply
can't be sent in the same turn as the inbound message (unlike teams-agent,
which replies synchronously). Every inbound activity's ConversationReference
is saved (see src/utils/teams_conversations.py) so src/utils/teams_notify.py
can resume the conversation later from job_queue.py / assistant.py's thread
fallback, exactly like WhatsApp/Slack's async notify path.

Config, the adapter, and botbuilder integration classes are imported lazily
inside the route handler rather than at module top, matching this file's own
CRITICAL rule about src/nodes/__init__.py (avoid pulling heavy imports in at
process startup) and teams-agent's own app.py convention.
"""

import logging
import os

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["teams"])

_adapter = None


def _get_adapter():
    global _adapter
    if _adapter is None:
        from botbuilder.integration.aiohttp import CloudAdapter, ConfigurationBotFrameworkAuthentication

        class _BotFrameworkConfig:
            """Attribute names are fixed by ConfigurationBotFrameworkAuthentication's
            contract — this only adapts env vars to that contract."""
            APP_ID = os.environ.get("MICROSOFT_APP_ID", "")
            APP_PASSWORD = os.environ.get("MICROSOFT_APP_PASSWORD", "")
            APP_TYPE = os.environ.get("MICROSOFT_APP_TYPE", "SingleTenant")
            APP_TENANTID = os.environ.get("MICROSOFT_APP_TENANT_ID", "")

        _adapter = CloudAdapter(ConfigurationBotFrameworkAuthentication(_BotFrameworkConfig()))
    return _adapter


async def _download_attachment(attachment) -> tuple[str | None, bytes | None]:
    """Best-effort attachment download. Teams delivers file attachments a few
    different ways depending on client/flow — this handles the common ones
    (inline image content, and the file-download-info card produced once a
    user accepts the file-consent prompt) and returns (None, None) rather than
    raising when it hits a shape it doesn't recognise, so a message with an
    attachment we can't resolve still reaches the user as a text-only turn
    instead of dropping the whole request.
    """
    import httpx

    content_type = getattr(attachment, "content_type", "") or ""
    name = getattr(attachment, "name", None) or "teams-attachment"

    download_url = None
    if content_type == "application/vnd.microsoft.teams.file.download.info":
        content = getattr(attachment, "content", None) or {}
        download_url = content.get("downloadUrl") if isinstance(content, dict) else None
    elif content_type.startswith("image/"):
        download_url = getattr(attachment, "content_url", None)

    if not download_url:
        return None, None

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(download_url)
            resp.raise_for_status()
            return name, resp.content
    except Exception as e:
        logger.warning("Teams attachment download failed for %s: %s", name, e)
        return None, None


def _get_bot():
    from botbuilder.core import ActivityHandler, TurnContext
    from botbuilder.schema import Activity, ActivityTypes

    class TeamsIngestBot(ActivityHandler):
        async def on_message_activity(self, turn_context: TurnContext):
            from src.nodes.assistant import handle_message
            from src.utils.teams_conversations import save_conversation_reference

            activity = turn_context.activity
            user_id = activity.conversation.id
            body = (activity.text or "").strip()

            # Persist the ConversationReference on every turn (cheap — Table Storage
            # upsert) so a pipeline dispatched from this message can notify the user
            # later, well outside this turn's lifetime.
            reference = TurnContext.get_conversation_reference(activity)
            save_conversation_reference(user_id, reference.as_dict())

            # Diagnostic (2026-09-12): unconditional, to see the real shape of a
            # OneDrive/SharePoint file share — the first probe (logging only inside
            # `if activity.attachments`) found attachments was EMPTY even with a
            # visible file card in Teams, meaning the file link travels some other
            # way (text/HTML, entities, channelData) that needs to be seen directly.
            try:
                # .warning(), not .info() — this env's effective log level filters
                # out .info() entirely (confirmed: only .warning()+ calls from this
                # module ever appeared in the App Service log stream).
                logger.warning(
                    "Teams activity dump: text=%r attachments=%r entities=%r channel_data=%r value=%r",
                    activity.text,
                    [a.as_dict() for a in (activity.attachments or [])],
                    [e.as_dict() for e in (activity.entities or [])],
                    activity.channel_data,
                    activity.value,
                )
            except Exception:
                logger.exception("Teams activity dump failed")

            file_name, file_bytes = None, None
            if activity.attachments:
                for att in activity.attachments:
                    file_name, file_bytes = await _download_attachment(att)
                    if file_bytes:
                        break

            await turn_context.send_activity(Activity(type=ActivityTypes.typing))

            try:
                reply = handle_message(
                    user_id=user_id,
                    body=body,
                    channel="teams",
                    file_bytes=file_bytes,
                    file_name=file_name,
                )
            except Exception:
                logger.exception("Teams handle_message failed")
                reply = "Sorry, something went wrong processing that. Please try again."

            await turn_context.send_activity(reply)

    return TeamsIngestBot()


_bot = None


@router.post("/messages")
async def messages(request: Request):
    from botbuilder.core import TurnContext
    from botbuilder.schema import Activity

    global _bot

    if "application/json" not in request.headers.get("Content-Type", ""):
        raise HTTPException(status_code=415)

    adapter = _get_adapter()
    if _bot is None:
        _bot = _get_bot()

    body = await request.json()
    activity = Activity().deserialize(body)
    auth_header = request.headers.get("Authorization", "")

    async def call_bot(turn_context: TurnContext):
        await _bot.on_turn(turn_context)

    try:
        response = await adapter.process_activity(auth_header, activity, call_bot)
    except Exception:
        logger.exception("Teams activity processing failed")
        raise HTTPException(status_code=500)

    if response:
        return JSONResponse(content=response.body, status_code=response.status)
    return Response(status_code=201)
