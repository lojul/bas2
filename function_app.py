"""Azure Functions entry point for Document Processor v2.

Triggers:
- Queue: Consumes pipeline jobs enqueued by the assistant (WhatsApp via n8n)
- HTTP:  Health check
"""

import json
import logging
import os
from datetime import datetime

import azure.functions as func

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

app = func.FunctionApp()


@app.queue_trigger(
    arg_name="msg",
    queue_name="pipeline-jobs",
    connection="AzureWebJobsStorage",
)
def pipeline_job_worker(msg: func.QueueMessage) -> None:
    """Consume pipeline jobs enqueued by the assistant (WhatsApp/n8n).

    Downloads file bytes from blob, runs the full pipeline, notifies the sender.
    Raising lets the Functions runtime retry (then poison-queue after 5 attempts).
    """
    payload = json.loads(msg.get_body().decode("utf-8"))
    logging.info("Pipeline job received: %s", payload.get("file_name") or "text")

    from src.utils.job_queue import run_pipeline_job
    run_pipeline_job(payload)


@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint."""
    return func.HttpResponse(
        json.dumps({
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
        }),
        mimetype="application/json",
    )
