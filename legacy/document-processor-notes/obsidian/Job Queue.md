# Job Queue

**File:** `langgraph/src/utils/job_queue.py`
**Azure resource:** Storage Queue `pipeline-jobs`

## Why it exists

App Service workers recycle on deploy or idle timeout. A daemon thread dies silently, losing the job. The queue survives restarts and gives 5 automatic retries before moving to the poison queue.

## Flow

```
[[Assistant]] (App Service)
   ↓ enqueue_pipeline_job()
   ├── file bytes → [[Azure Blob Storage]] (pipeline-jobs container)
   └── JSON message → Storage Queue
         ↓
[[Function App]] queue trigger (run_pipeline_job)
   ├── download bytes from blob
   ├── run [[Pipeline]]
   ├── delete blob
   └── notify user via [[WhatsApp Notify]]
```

## Payload fields

| Field | Purpose |
|---|---|
| `blob_name` | Blob key for file bytes |
| `file_name` | Display name |
| `text` | Pre-computed OCR text (forwarded posts) |
| `forced_type` | Skip classification |
| `skip_duplicate_check` | User confirmed "process anyway" |
| `notify_user` | WhatsApp number to notify on completion |
| `notify_channel` | `"whatsapp"` or `"dashboard"` |
| `sender_number` | WhatsApp sender number (stored on indexed document) |

## Failure handling

- 5 retries by Functions runtime
- Failed after 5 → moves to `pipeline-jobs-poison`
- [[Function App]] timer checks poison queue and alerts `ADMIN_WHATSAPP`

## Thread fallback

If queue unavailable (`PIPELINE_QUEUE_CONN` not set), falls back to daemon thread. Jobs can be lost on restart.

## Connects to

[[Assistant]] — producer
[[Function App]] — consumer
[[Pipeline]] — what runs
[[Azure Blob Storage]] — file staging
[[WhatsApp Notify]] — completion notification
