"""Send Slack messages via the Slack Web API (chat.postMessage).

Requires SLACK_BOT_TOKEN env var (xoxb-... Bot User OAuth Token) with
scopes: chat:write, files:read.
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

SLACK_API_BASE = "https://slack.com/api"


def send_slack(channel: str, text: str) -> bool:
    """Send a message to a Slack channel or DM (user ID or channel ID). Returns True on success."""
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    if not token or not channel or not text:
        return False
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                f"{SLACK_API_BASE}/chat.postMessage",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"channel": channel, "text": text},
            )
            data = resp.json()
            if not data.get("ok"):
                logger.warning("Slack notify failed: %s", data.get("error", "unknown"))
                return False
            return True
    except Exception as e:
        logger.warning("Slack notify error: %s", e)
        return False


def download_slack_file(url_private: str) -> bytes | None:
    """Download a file from Slack using the bot token. Returns raw bytes or None."""
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    if not token or not url_private:
        return None
    try:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            resp = client.get(
                url_private,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.content
    except Exception as e:
        logger.warning("Slack file download error for %s: %s", url_private, e)
        return None
