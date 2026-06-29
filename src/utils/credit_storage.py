"""Azure Table Storage — user credit balances."""

import logging
import os

logger = logging.getLogger(__name__)

_ACCOUNT = "blobhk04472"
_TABLE = "UserCredits"


def _client():
    from azure.data.tables import TableServiceClient
    sas = os.environ.get("AZURE_TABLE_SAS", "")
    if not sas:
        return None
    url = f"https://{_ACCOUNT}.table.core.windows.net/?{sas}"
    service = TableServiceClient(endpoint=url)
    try:
        return service.create_table_if_not_exists(_TABLE)
    except Exception:
        return service.get_table_client(_TABLE)


def get_balance(username: str) -> int:
    """Return current credit balance for a user (0 if not found)."""
    try:
        client = _client()
        if client is None:
            return 0
        entity = client.get_entity("credits", username)
        return int(entity.get("balance", 0))
    except Exception as e:
        if "ResourceNotFound" in type(e).__name__ or "404" in str(e):
            return 0
        logger.error("Failed to get balance for %s: %s", username, e)
        return 0


def add_credits(username: str, amount: int) -> int:
    """Add credits to a user's balance. Returns new balance."""
    client = _client()
    if client is None:
        logger.warning("AZURE_TABLE_SAS not set — skipping credit add")
        return 0

    try:
        entity = client.get_entity("credits", username)
        new_balance = int(entity.get("balance", 0)) + amount
        entity["balance"] = new_balance
        client.update_entity(entity)
        return new_balance
    except Exception as e:
        if "ResourceNotFound" in type(e).__name__ or "404" in str(e):
            new_balance = amount
            client.create_entity({
                "PartitionKey": "credits",
                "RowKey": username,
                "balance": new_balance,
            })
            return new_balance
        logger.error("Failed to add %d credits for %s: %s", amount, username, e)
        raise
