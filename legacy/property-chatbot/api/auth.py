"""Per-channel API key validation. Each channel adapter gets its own key,
independently revocable, same pattern as the org's existing SEARCH_API_KEY.
"""

from fastapi import HTTPException

from core.config import CHANNEL_API_KEYS


def _load_keys() -> dict[str, str]:
    keys = {}
    for pair in CHANNEL_API_KEYS.split(","):
        if ":" in pair:
            channel, key = pair.split(":", 1)
            keys[channel.strip()] = key.strip()
    return keys


def verify_channel_key(channel: str, x_api_key: str) -> None:
    keys = _load_keys()
    expected = keys.get(channel)
    if not expected or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key for channel")
