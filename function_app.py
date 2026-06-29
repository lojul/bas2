"""Azure Functions entry point for Document Processor.

One trigger:
- Timer: Runs every 5 minutes automatically, processes files from OneDrive /In
"""

import os
import json
import logging
import azure.functions as func
from datetime import datetime

# Set up paths for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from langsmith import traceable

from src.graph import process_file
from src.nodes.onedrive import list_onedrive_files, move_to_processed, get_access_token
from src.state import ProcessingStatus
import httpx

app = func.FunctionApp()


MAX_FILES_PER_RUN = 7  # Process max 7 files per run

_CONFIG_BLOB = "config/settings.json"
_CONFIG_DEFAULTS = {
    "inbox_folder": "/Document Processor/In",
    "move_when_done": False,
    "timer_enabled": True,
}


def _load_blob_config() -> dict:
    """Read runtime config from Azure Blob. Falls back to defaults."""
    account = os.environ.get("AZURE_BLOB_ACCOUNT")
    container = os.environ.get("AZURE_BLOB_CONTAINER", "property-pdf")
    sas = os.environ.get("AZURE_BLOB_WRITE_SAS", "")
    if not account:
        return _CONFIG_DEFAULTS.copy()
    url = f"https://{account}.blob.core.windows.net/{container}/{_CONFIG_BLOB}?{sas}"
    try:
        with httpx.Client(timeout=5) as client:
            r = client.get(url)
            if r.status_code == 200:
                return {**_CONFIG_DEFAULTS, **r.json()}
    except Exception:
        pass
    return _CONFIG_DEFAULTS.copy()


@traceable(name="run_processor", run_type="chain")
def run_processor(move_when_done: bool | None = None) -> dict:
    """Core processing logic shared by both triggers."""
    cfg = _load_blob_config()

    drive_id = os.environ.get("MS_GRAPH_DRIVE_ID")
    inbox_folder = cfg.get("inbox_folder") or os.environ.get("MS_GRAPH_INBOX_FOLDER", "/Document Processor/In")
    if move_when_done is None:
        move_when_done = cfg.get("move_when_done", False)

    # List files in inbox folder
    files = list_onedrive_files(
        drive_id,
        inbox_folder,
        file_extensions=[".pdf", ".jpg", ".jpeg", ".png"]
    )

    if not files:
        return {
            "status": "ok",
            "message": "No files to process",
            "processed": 0,
            "files": []
        }

    # Limit to MAX_FILES_PER_RUN to avoid timeout
    total_files = len(files)
    files = files[:MAX_FILES_PER_RUN]
    remaining = total_files - len(files)

    # Get Processed folder ID if needed
    processed_folder_id = None
    processed_folder = os.environ.get("MS_GRAPH_PROCESSED_FOLDER", "/Document Processor/Processed")
    if move_when_done:
        try:
            token = get_access_token()
            headers = {"Authorization": f"Bearer {token}"}
            folder_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:{processed_folder}"

            with httpx.Client() as client:
                resp = client.get(folder_url, headers=headers)
                resp.raise_for_status()
                processed_folder_id = resp.json()["id"]
        except Exception as e:
            logging.warning(f"Could not get Processed folder: {e}")

    # Process each file
    results = []
    success_count = 0
    error_count = 0

    for file in files:
        file_id = file["id"]
        file_name = file["name"]

        logging.info(f"Processing: {file_name}")

        try:
            # Run through LangGraph workflow
            result = process_file(file_id, file_name)

            if result.status == ProcessingStatus.ERROR:
                error_count += 1
                results.append({
                    "file": file_name,
                    "status": "error",
                    "error": result.error_message
                })
            else:
                success_count += 1
                results.append({
                    "file": file_name,
                    "status": "success",
                    "type": result.document_type.value if result.document_type else "unknown",
                    "confidence": result.classification_confidence
                })

                # Move to Processed
                if move_when_done and processed_folder_id:
                    try:
                        move_to_processed(drive_id, file_id, processed_folder_id)
                        logging.info(f"Moved to /Processed: {file_name}")
                    except Exception as e:
                        logging.warning(f"Failed to move {file_name}: {e}")

        except Exception as e:
            error_count += 1
            results.append({
                "file": file_name,
                "status": "error",
                "error": str(e)
            })
            logging.error(f"Error processing {file_name}: {e}")

    return {
        "status": "ok",
        "message": f"Processed {len(files)} file(s)" + (f", {remaining} remaining" if remaining > 0 else ""),
        "processed": len(files),
        "success": success_count,
        "errors": error_count,
        "remaining": remaining,
        "files": results
    }


@app.timer_trigger(
    schedule="0 */5 * * * *",  # Every 5 minutes
    arg_name="timer",
    run_on_startup=False
)
def timer_trigger(timer: func.TimerRequest) -> None:
    """Timer trigger - runs every 5 minutes.

    Checks OneDrive /In folder and processes any new files.
    Skips if timer_enabled is set to false in blob config.
    """
    cfg = _load_blob_config()
    if not cfg.get("timer_enabled", True):
        logging.info("Timer trigger disabled via Settings — skipping.")
        return

    logging.info("Timer trigger started")

    if timer.past_due:
        logging.info("Timer is past due, running anyway")

    try:
        result = run_processor(move_when_done=cfg.get("move_when_done", False))
        logging.info(f"Timer trigger completed: {result['message']}")
    except Exception as e:
        logging.error(f"Timer trigger failed: {e}")
        raise



@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint."""
    return func.HttpResponse(
        json.dumps({
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat()
        }),
        mimetype="application/json"
    )
