# Function App

**File:** `langgraph/function_app.py`
**Azure resource:** `c21net-bas-func-doc-pipeline-ea-prod`

## Triggers

| Trigger | Schedule / Event | What it does |
|---|---|---|
| Timer | Every 5 min | Fetch up to 7 files from OneDrive `/In`, run [[Pipeline]] for each |
| Queue | `pipeline-jobs` | Consume one [[Job Queue]] message, run [[Pipeline]], notify via [[WhatsApp Notify]] |
| HTTP GET `/api/health` | On request | Health check (anonymous) |

## Timer trigger detail

```
List files in OneDrive /In (Microsoft Graph)
   ↓ (up to 7 per batch)
For each file:
   check [[DI Guard]] (daily OCR page limit)
   ↓
   run [[Pipeline]] (process_file)
   ↓
   if MOVE_WHEN_DONE=true → move to /Processed
   ↓
check [[Job Queue]] poison queue → alert ADMIN_WHATSAPP if non-empty
```

## Queue trigger detail

```
Receive message from pipeline-jobs queue
   ↓
run_pipeline_job(payload)  ←  see [[Job Queue]]
   ↓
[[Pipeline]] runs
   ↓
[[WhatsApp Notify]] → user
```

## Deploy

```bash
cd langgraph
func azure functionapp publish c21net-bas-func-doc-pipeline-ea-prod --python
```

`.funcignore` is required — without it, uploads `.venv/` (918MB) and deploys stale code.

## Connects to

[[Pipeline]] — runs it
[[Job Queue]] — consumes messages
[[OneDrive]] — reads files from /In
[[DI Guard]] — cost protection
[[WhatsApp Notify]] — completion alerts
