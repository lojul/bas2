"""Channel-agnostic completion-notify dispatch.

Both the assistant's thread fallback (src/nodes/assistant.py) and the durable
queue worker (src/utils/job_queue.py, Function App) need to push a pipeline
completion message back to the user on whichever channel they came from.
This is the single place that maps a channel name to its delivery function —
to support notifying a new channel (e.g. Teams), register it here once
instead of adding another if/elif in both callers.

Channels with no registered delivery function (e.g. "dashboard", where the
reply is already returned synchronously in the HTTP response) are a no-op.
"""


def _whatsapp(target: str, message: str) -> bool:
    from src.utils.whatsapp_notify import send_whatsapp
    return send_whatsapp(target, message)


def _slack(target: str, message: str) -> bool:
    from src.utils.slack_notify import send_slack
    return send_slack(target, message)


def _teams(target: str, message: str) -> bool:
    from src.utils.teams_notify import send_teams
    return send_teams(target, message)


_NOTIFIERS = {
    "whatsapp": _whatsapp,
    "slack": _slack,
    "teams": _teams,
}


def notify(channel: str, target: str | None, message: str) -> bool:
    """Send an async completion notification to the user on their channel.
    Returns False (no-op) if the target is empty or the channel has no
    registered delivery function."""
    if not target:
        return False
    sender = _NOTIFIERS.get(channel)
    return sender(target, message) if sender else False
