"""Azure Functions entry point for the Odoo -> BAS properties-index sync job.

Standalone from document-processor and bas-stacks (see project-odoo-to-bas-sync memory).
Daily timer job: reads x_c21_listing records where x_c21_published=False, embeds them,
upserts into BAS's properties-index, flips the flag back to True.

Triggers:
- Timer: daily sync run
- HTTP:  health check + manual trigger (for testing without waiting on the schedule)
"""

import logging
import os
from datetime import datetime, timezone

import azure.functions as func

app = func.FunctionApp()


@app.timer_trigger(
    schedule="0 0 18 * * *",  # 18:00 UTC daily — adjust to taste, no fixed requirement yet
    arg_name="myTimer",
    run_on_startup=False,
    use_monitor=True,
)
def daily_sync(myTimer: func.TimerRequest) -> None:
    """Daily Odoo -> BAS properties-index sync.

    Scaffold only — see run_sync() below for the actual work, not yet implemented.
    """
    if myTimer.past_due:
        logging.warning("daily_sync: timer is past due")

    logging.info("daily_sync: starting run at %s", datetime.now(timezone.utc).isoformat())
    run_sync()


@app.route(route="sync", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def manual_sync(req: func.HttpRequest) -> func.HttpResponse:
    """Manually trigger a sync run without waiting for the timer schedule."""
    logging.info("manual_sync: triggered via HTTP")
    run_sync()
    return func.HttpResponse("Sync run triggered.", status_code=200)


@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint."""
    import json

    return func.HttpResponse(
        json.dumps({
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
        mimetype="application/json",
    )


def run_sync() -> None:
    """Read Odoo x_c21_listing records needing (re-)sync, embed, upsert to BAS,
    flip x_c21_published back to True.
    """
    from bas_sync import embed, upsert
    from mapping import build_content, map_listing
    from odoo_client import OdooClient

    odoo = OdooClient()
    records = odoo.fetch_pending()

    # SYNC_MAX_RECORDS: optional cap for controlled first runs. Unset = no limit.
    max_records = os.environ.get("SYNC_MAX_RECORDS")
    if max_records:
        records = records[: int(max_records)]

    logging.info("run_sync: %d record(s) pending", len(records))

    succeeded = 0
    for record in records:
        record_id = record["id"]
        try:
            doc = map_listing(record)
            doc["contentVector"] = embed(build_content(record))
            upsert(doc)
            odoo.mark_published(record_id)
            succeeded += 1
        except Exception:
            logging.exception("run_sync: failed on Odoo record %s", record_id)

    logging.info("run_sync: done, %d/%d succeeded", succeeded, len(records))
