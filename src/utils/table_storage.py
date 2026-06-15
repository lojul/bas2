"""Azure Table Storage — permanent processing history log."""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_ACCOUNT = "blobhk04472"
_TABLE = "ProcessingHistory"


def _client():
    from azure.data.tables import TableServiceClient
    sas = os.environ.get("AZURE_TABLE_SAS", "")
    if not sas:
        return None
    url = f"https://{_ACCOUNT}.table.core.windows.net/?{sas}"
    return TableServiceClient(endpoint=url).get_table_client(_TABLE)


def log_run(
    file_name: str,
    document_type: str,
    status: str,           # "success" | "error"
    duration_ms: int,
    extracted_data: dict | None = None,
    error_message: str | None = None,
    index_id: str | None = None,
) -> None:
    """Write one processing run record to ProcessingHistory table."""
    try:
        client = _client()
        if client is None:
            logger.warning("AZURE_TABLE_SAS not set — skipping history log")
            return

        now = datetime.now(timezone.utc)
        # PartitionKey = YYYY-MM for easy monthly queries
        partition_key = now.strftime("%Y-%m")
        row_key = f"{now.strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}"

        entity = {
            "PartitionKey": partition_key,
            "RowKey": row_key,
            "file_name": file_name,
            "document_type": document_type or "unknown",
            "status": status,
            "duration_ms": duration_ms,
            "processed_at": now.isoformat(),
            "extracted_data": json.dumps(extracted_data or {}, ensure_ascii=False),
            "error_message": error_message or "",
            "index_id": index_id or "",
        }
        client.create_entity(entity)
    except Exception as e:
        # Never crash the pipeline over a logging failure
        logger.error("Failed to log run to Table Storage: %s", e)


def log_unsupported(file_name: str, ext: str) -> None:
    """Log a file with an unsupported format to ProcessingHistory."""
    log_run(
        file_name=file_name,
        document_type=f"unsupported_{ext}" if ext else "unsupported",
        status="unsupported",
        duration_ms=0,
    )


def list_runs(months: int = 3, top: int = 500) -> list[dict]:
    """Return recent runs from ProcessingHistory, newest first."""
    try:
        client = _client()
        if client is None:
            return []

        now = datetime.now(timezone.utc)
        # Build partition key filters for the last N months
        partitions = set()
        for i in range(months + 1):
            m = now.month - i
        y = now.year
        for i in range(months + 1):
            m = now.month - i
            yr = now.year
            while m <= 0:
                m += 12
                yr -= 1
            partitions.add(f"{yr}-{m:02d}")

        filter_parts = " or ".join(
            f"PartitionKey eq '{p}'" for p in sorted(partitions, reverse=True)
        )
        entities = list(client.query_entities(filter_parts, results_per_page=top))

        runs = []
        for e in entities:
            try:
                extracted = json.loads(e.get("extracted_data") or "{}")
            except Exception:
                extracted = {}
            runs.append({
                "row_key": e["RowKey"],
                "file_name": e.get("file_name", ""),
                "document_type": e.get("document_type", "unknown"),
                "status": e.get("status", "unknown"),
                "duration_ms": e.get("duration_ms", 0),
                "processed_at": e.get("processed_at", ""),
                "extracted_data": extracted,
                "error_message": e.get("error_message", ""),
                "index_id": e.get("index_id", ""),
            })

        # Sort newest first
        runs.sort(key=lambda r: r["processed_at"], reverse=True)
        return runs[:top]
    except Exception as e:
        logger.error("Failed to read from Table Storage: %s", e)
        return []
