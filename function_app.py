"""Azure Functions entry point for Document Processor.

Two triggers:
- Timer: Runs every 5 minutes automatically
- HTTP: Manual trigger via URL or dashboard button
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


@traceable(name="run_processor", run_type="chain")
def run_processor(move_when_done: bool = True) -> dict:
    """Core processing logic shared by both triggers.

    Args:
        move_when_done: Move files to /Processed after processing

    Returns:
        Summary dict with counts and file names
    """
    drive_id = os.environ.get("MS_GRAPH_DRIVE_ID")
    inbox_folder = os.environ.get("MS_GRAPH_INBOX_FOLDER", "/Document Processor/In")

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
    """
    logging.info("Timer trigger started")

    if timer.past_due:
        logging.info("Timer is past due, running anyway")

    try:
        result = run_processor(move_when_done=True)  # Move to /Processed after success
        logging.info(f"Timer trigger completed: {result['message']}")
    except Exception as e:
        logging.error(f"Timer trigger failed: {e}")
        raise


@app.route(route="process", methods=["POST", "GET"], auth_level=func.AuthLevel.ANONYMOUS)
def http_trigger(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP trigger - manual processing on demand.

    Call this URL to trigger immediate processing.
    Supports both GET (browser) and POST (API).
    """
    logging.info("HTTP trigger started")

    try:
        # Check if move_when_done is specified (disabled for testing)
        move_when_done = req.params.get("move", "false").lower() == "true"

        result = run_processor(move_when_done=move_when_done)

        return func.HttpResponse(
            json.dumps(result, indent=2),
            status_code=200,
            mimetype="application/json",
            headers={
                "Access-Control-Allow-Origin": "*",  # Allow dashboard to call
                "Access-Control-Allow-Methods": "GET, POST"
            }
        )
    except Exception as e:
        logging.error(f"HTTP trigger failed: {e}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": str(e)}),
            status_code=500,
            mimetype="application/json"
        )


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
