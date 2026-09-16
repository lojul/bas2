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


@app.timer_trigger(schedule="0 0 23 * * *", arg_name="timer", run_on_startup=False)
def onedrive_sync(timer: func.TimerRequest) -> None:
    """Pick up new files dropped in the watched OneDrive folder and feed them
    into the same pipeline queue WhatsApp/Slack/Teams use.

    Once daily (23:00 UTC = 07:00 HKT) — matches the sibling bas-stacks
    project's onedrive-sync cadence (`0 0 7 * * *` there, but with
    WEBSITE_TIME_ZONE=Asia/Singapore instead of the UTC offset baked into
    the cron itself; this Function App has no WEBSITE_TIME_ZONE set and
    Linux Function Apps run cron in raw UTC, confirmed the hard way when the
    daily digest below first fired at the wrong hour — so the offset is
    baked in here too, not left to an app setting). OneDrive doesn't need
    WhatsApp/Slack/Teams-level responsiveness, so a daily check is enough;
    was every 10 minutes during initial testing.

    Delta-based (Microsoft Graph /delta), not a folder listing — only ever
    processes files added/changed since the last saved delta link, so the
    existing backlog is never touched. See src/utils/onedrive_delta_store.py
    and scripts/onedrive_baseline_delta.py for the one-time setup step.

    Hard-stops (raises, no auto full re-sync) if the delta link is missing or
    expired — a silent full resync would re-OCR the whole watched folder.
    Off by default (ONEDRIVE_SYNC_ENABLED); inert until explicitly enabled
    after the baseline has been established.
    """
    if os.environ.get("ONEDRIVE_SYNC_ENABLED", "false").lower() != "true":
        return

    from datetime import datetime as dt, timedelta, timezone

    from src.utils.graph_client import DeltaLinkExpiredError, GraphClient
    from src.utils.job_queue import enqueue_pipeline_job
    from src.utils.onedrive_delta_store import load_delta_link, save_delta_link
    from src.utils.supported_formats import SUPPORTED_FORMATS

    delta_link = load_delta_link()
    if delta_link is None:
        logging.error(
            "onedrive_resync_blocked reason=no_delta_link — refusing to full-resync; "
            "run scripts/onedrive_baseline_delta.py to establish the baseline deliberately."
        )
        raise RuntimeError("OneDrive sync halted: no delta link and full re-sync is disabled.")

    drive_id = os.environ["ONEDRIVE_SYNC_DRIVE_ID"]
    graph = GraphClient()
    max_age_days = int(os.environ.get("ONEDRIVE_SYNC_MAX_AGE_DAYS", "90"))
    max_file_mb = float(os.environ.get("ONEDRIVE_MAX_FILE_MB", "25"))
    since = dt.now(timezone.utc) - timedelta(days=max_age_days)

    try:
        items, new_delta_link = graph.iter_delta_changes(drive_id, "", delta_link, since=since)
    except DeltaLinkExpiredError:
        logging.error(
            "onedrive_resync_blocked reason=delta_link_expired — refusing to full-resync; "
            "re-baseline via scripts/onedrive_baseline_delta.py deliberately."
        )
        raise RuntimeError(
            "OneDrive sync halted: delta link expired (410) and full re-sync is disabled."
        ) from None

    logging.info("OneDrive sync: found %d changed file(s).", len(items))

    enqueued, skipped = 0, 0
    for item in items:
        name = item.get("name", "")
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        size_mb = item.get("size", 0) / (1024 * 1024)
        if ext not in SUPPORTED_FORMATS:
            logging.info("OneDrive sync: skipping unsupported format '%s' (%s)", ext, name)
            skipped += 1
            continue
        if size_mb > max_file_mb:
            logging.info("OneDrive sync: skipping oversized file %s (%.1fMB)", name, size_mb)
            skipped += 1
            continue

        try:
            download_url = item.get("@microsoft.graph.downloadUrl") or graph.get_download_url(
                drive_id, item["id"]
            )
            if not download_url:
                logging.warning("OneDrive sync: no download URL for %s — skipping.", name)
                skipped += 1
                continue
            file_bytes = graph.download(download_url)
            enqueue_pipeline_job(
                file_bytes, name,
                notify_channel="", notify_user="",
                source="onedrive",
            )
            enqueued += 1
        except Exception as exc:
            logging.error("OneDrive sync: failed to enqueue %s: %s", name, exc)

    # Only advance the delta link once every returned item has been handled —
    # a partial failure here must not silently skip files on the next run.
    save_delta_link(new_delta_link)
    logging.info("OneDrive sync complete — enqueued: %d, skipped: %d", enqueued, skipped)


@app.timer_trigger(schedule="0 55 15 * * *", arg_name="timer", run_on_startup=False)
def daily_processing_summary(timer: func.TimerRequest) -> None:
    """Post a once-daily rollup of today's processing volume to Slack.

    Schedule is 15:55 UTC = 23:55 Hong Kong time — Linux Function Apps run
    cron schedules in UTC regardless of WEBSITE_TIME_ZONE, so the HKT offset
    is baked into the cron expression itself, not left to app settings.

    Always sends, even when nothing processed today — that's the point: a
    missing message is itself the signal that the schedule (or the app) has
    stopped running, not just "nothing happened."

    No per-document notification exists for OneDrive-triggered files (there's
    no WhatsApp/Slack sender to reply to), so this is the visibility
    mechanism: how many documents ran today, broken down by source (manual
    WhatsApp/Slack/Teams upload vs. OneDrive schedule), and how close to the
    DI daily page cap. The manual/OneDrive split depends on DocumentState's
    `source` field being persisted per run — see
    src/utils/table_storage.py:log_run().
    """
    channel = os.environ.get("ADMIN_SLACK_CHANNEL", "")
    if not channel:
        return

    from datetime import datetime as dt, timezone

    from src.utils.di_guard import get_usage_today
    from src.utils.slack_notify import send_slack
    from src.utils.table_storage import count_runs_today

    counts = count_runs_today()
    pages_used = get_usage_today()
    di_limit = int(os.environ.get("DI_DAILY_PAGE_LIMIT", "200"))

    # No reliable "was this a manual admin-API invocation" flag on a Python
    # timer trigger — approximate it by checking whether we actually fired
    # near the scheduled 15:55 UTC slot. Lets a manual test run (e.g. to
    # verify Slack delivery without waiting for the schedule) be told apart
    # from the real nightly run in the message itself.
    now = dt.now(timezone.utc)
    scheduled_minutes = 15 * 60 + 55
    now_minutes = now.hour * 60 + now.minute
    run_kind = "定時排程 Scheduled" if abs(now_minutes - scheduled_minutes) <= 5 else "手動觸發 Manual/test run"

    lines = [
        f"📊 Document Processor — 今日處理摘要（{run_kind}）",
        f"成功：{counts.get('success', 0)} | 失敗：{counts.get('error', 0)} | 不支援：{counts.get('unsupported', 0)}",
        f"　人手上傳（WhatsApp/Slack/Teams）：成功 {counts.get('manual_success', 0)} | 失敗 {counts.get('manual_error', 0)}",
        f"　OneDrive 排程：成功 {counts.get('onedrive_success', 0)} | 失敗 {counts.get('onedrive_error', 0)}",
        f"OCR 頁數：{pages_used}/{di_limit}",
    ]
    send_slack(channel, "\n".join(lines))
