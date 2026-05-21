"""Simple JSON store for tracking processed documents."""

import json
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

STORE_PATH = Path(__file__).parent.parent / "data" / "processed.json"


@dataclass
class ProcessedFile:
    """Record of a processed file."""
    file_name: str
    status: str  # "success" or "error"
    document_type: str  # "listing", "news", "contact", "unknown"
    text_preview: str
    text_length: int
    tables_count: int
    figures_count: int
    processed_at: str
    error_message: str = ""


def _ensure_store():
    """Ensure store directory and file exist."""
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not STORE_PATH.exists():
        STORE_PATH.write_text("[]")


def save_result(record: ProcessedFile):
    """Save a processing result to the store."""
    _ensure_store()

    data = json.loads(STORE_PATH.read_text())
    data.append(asdict(record))

    # Keep only last 100 records
    if len(data) > 100:
        data = data[-100:]

    STORE_PATH.write_text(json.dumps(data, indent=2))


def get_all_results() -> list[dict]:
    """Get all processing results."""
    _ensure_store()
    return json.loads(STORE_PATH.read_text())


def get_today_results() -> list[dict]:
    """Get today's processing results."""
    today = datetime.now().strftime("%Y-%m-%d")
    return [r for r in get_all_results() if r["processed_at"].startswith(today)]


def get_stats() -> dict:
    """Get summary statistics."""
    results = get_all_results()
    today_results = get_today_results()

    return {
        "total": len(results),
        "today": len(today_results),
        "success": len([r for r in results if r["status"] == "success"]),
        "errors": len([r for r in results if r["status"] == "error"]),
        "today_success": len([r for r in today_results if r["status"] == "success"]),
        "today_errors": len([r for r in today_results if r["status"] == "error"]),
        "by_type": {
            "listing": len([r for r in results if r["document_type"] == "listing"]),
            "news": len([r for r in results if r["document_type"] == "news"]),
            "contact": len([r for r in results if r["document_type"] == "contact"]),
            "unknown": len([r for r in results if r["document_type"] == "unknown"]),
        }
    }


def clear_store():
    """Clear all records (for testing)."""
    _ensure_store()
    STORE_PATH.write_text("[]")
