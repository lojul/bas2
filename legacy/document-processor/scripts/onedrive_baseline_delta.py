"""One-time manual step: establish the OneDrive delta-sync baseline.

Run this BEFORE setting ONEDRIVE_SYNC_ENABLED=true, and again any time the
watched drive/folder changes (ONEDRIVE_SYNC_DRIVE_ID / ONEDRIVE_SYNC_FOLDER_PATH).
It does a full traversal of the watched folder, but DISCARDS every item it
finds — it only saves the resulting delta link. That sets the baseline to
"now", so the onedrive_sync timer function will only ever pick up files
added/changed after this point. The existing backlog is never touched.

Usage:
    cd langgraph && source .venv/bin/activate
    python scripts/onedrive_baseline_delta.py

Safe to re-run: it will always overwrite the saved delta link with a fresh
"now" baseline (use scripts/onedrive_baseline_delta.py --force to skip the
confirmation prompt when a delta link already exists).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.utils.graph_client import GraphClient
from src.utils.onedrive_delta_store import load_delta_link, save_delta_link


def main() -> None:
    force = "--force" in sys.argv

    existing = load_delta_link()
    if existing and not force:
        answer = input(
            "A delta link already exists — re-running will reset the baseline "
            "to now (existing files remain untouched, but the previous "
            "baseline point is lost). Continue? [y/N] "
        )
        if answer.strip().lower() != "y":
            print("Aborted.")
            return

    drive_id = os.environ["ONEDRIVE_SYNC_DRIVE_ID"]
    inbox_folder = os.environ["ONEDRIVE_SYNC_FOLDER_PATH"]

    graph = GraphClient()
    print(f"Resolving folder '{inbox_folder}'...")
    item_id = graph.get_item_id_by_path(drive_id, inbox_folder)
    print(f"Folder item ID: {item_id}")

    print("Running full traversal to establish baseline (items are discarded)...")
    items, delta_link = graph.iter_delta_changes(drive_id, item_id, delta_link=None)

    print(f"Found {len(items)} existing file(s) — these will NOT be processed.")
    save_delta_link(delta_link)
    print("Baseline saved. The onedrive_sync timer will only pick up files added from now on.")
    print("Set ONEDRIVE_SYNC_ENABLED=true on the Function App to activate it.")


if __name__ == "__main__":
    main()
