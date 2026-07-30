"""Slack adapter — thin translation layer only. See README.md for why this is
two functions (fast ack + async worker) instead of one.
"""

import hashlib
import hmac
import json
import logging
import os
import time

import azure.functions as func
import httpx
from azure.storage.queue import QueueClient, TextBase64EncodePolicy

app = func.FunctionApp()

SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
CHATBOT_API_URL = os.environ.get(
    "CHATBOT_API_URL", "https://c21net-bas-api-property-chatbot-ea-prod.azurewebsites.net/api/v1/chat"
)
CHATBOT_API_KEY = os.environ.get("CHATBOT_API_KEY", "")
QUEUE_NAME = "slack-events"


def _verify_slack_signature(req: func.HttpRequest) -> bool:
    """HMAC verification per Slack's signing spec — rejects anything not
    genuinely from Slack, and anything older than 5 minutes (replay guard).
    """
    timestamp = req.headers.get("X-Slack-Request-Timestamp", "")
    if not timestamp:
        return False
    try:
        if abs(time.time() - int(timestamp)) > 60 * 5:
            return False
    except ValueError:
        return False

    body = req.get_body().decode("utf-8")
    basestring = f"v0:{timestamp}:{body}"
    computed = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode(), basestring.encode(), hashlib.sha256
    ).hexdigest()
    slack_sig = req.headers.get("X-Slack-Signature", "")
    return hmac.compare_digest(computed, slack_sig)


@app.route(route="slack/events", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def slack_events(req: func.HttpRequest) -> func.HttpResponse:
    if not _verify_slack_signature(req):
        return func.HttpResponse("Invalid signature", status_code=401)

    # Slack retries an event (up to 3x) if it doesn't get an ack within ~3s —
    # a slow cold start alone can trigger this. Retried deliveries carry this
    # header; skip re-enqueueing so a slow first ack doesn't cause duplicate
    # replies (found in production testing: a 30s+ cold start produced 3
    # retries, 2 of which succeeded and posted duplicate answers).
    if req.headers.get("X-Slack-Retry-Num"):
        logging.info("slack_events: ignoring Slack retry #%s", req.headers.get("X-Slack-Retry-Num"))
        return func.HttpResponse("", status_code=200)

    body = req.get_json()

    # Slack's one-time setup check — must echo the challenge back verbatim.
    if body.get("type") == "url_verification":
        return func.HttpResponse(
            json.dumps({"challenge": body["challenge"]}), mimetype="application/json"
        )

    event = body.get("event", {})
    is_message = event.get("type") in ("message", "app_mention")
    # bot_id present = this is our own bot's message (avoid replying to ourselves).
    # subtype present = edits/deletes/joins, not a real new message.
    if is_message and not event.get("bot_id") and not event.get("subtype"):
        # message_encode_policy=TextBase64EncodePolicy() is required — the
        # Functions host's queue trigger expects Base64-encoded messages
        # (QueuesOptions.MessageEncoding=Base64). Without it, the SDK sends
        # plain text, the host silently fails to decode it before even
        # invoking slack_worker, and the message poison-queues after 5
        # retries with no exception ever logged (found by testing directly —
        # same pattern used by document-processor's own job_queue.py).
        queue_client = QueueClient.from_connection_string(
            os.environ["AzureWebJobsStorage"], QUEUE_NAME,
            message_encode_policy=TextBase64EncodePolicy(),
        )
        try:
            queue_client.create_queue()
        except Exception:
            pass  # already exists — fine
        queue_client.send_message(json.dumps(event))

    # Ack fast regardless — Slack requires a response within 3 seconds.
    return func.HttpResponse("", status_code=200)


@app.queue_trigger(arg_name="msg", queue_name=QUEUE_NAME, connection="AzureWebJobsStorage")
def slack_worker(msg: func.QueueMessage) -> None:
    event = json.loads(msg.get_body().decode("utf-8"))
    channel = event.get("channel")
    user = event.get("user")
    text = event.get("text", "")
    if not channel or not user or not text:
        logging.warning("slack_worker: incomplete event, skipping: %s", event)
        return

    conversation_id = f"slack:{channel}/{user}"
    try:
        resp = httpx.post(
            CHATBOT_API_URL,
            json={"channel": "slack", "conversation_id": conversation_id, "message": text},
            headers={"x-api-key": CHATBOT_API_KEY},
            timeout=90,
        )
        resp.raise_for_status()
        reply = resp.json()["reply"]
    except Exception:
        logging.exception("slack_worker: chatbot call failed")
        reply = "Sorry, something went wrong answering that. Please try again shortly."

    try:
        httpx.post(
            "https://slack.com/api/chat.postMessage",
            json={"channel": channel, "text": reply},
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            timeout=30,
        )
    except Exception:
        logging.exception("slack_worker: failed to post reply back to Slack")
