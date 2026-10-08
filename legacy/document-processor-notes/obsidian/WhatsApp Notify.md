# WhatsApp Notify

**File:** `langgraph/src/utils/whatsapp_notify.py`
**Env var:** `N8N_NOTIFY_WEBHOOK_URL`

## Flow

```
send_whatsapp(number, message)
   ↓
POST N8N_NOTIFY_WEBHOOK_URL
   ↓
n8n "WhatsApp Notify" workflow
   ↓
Twilio API
   ↓
WhatsApp user
```

## Who calls it

| Caller | When |
|---|---|
| [[Job Queue]] worker | Pipeline job completed or failed |
| [[Function App]] timer | Poison queue alert to ADMIN_WHATSAPP |
| [[DI Guard]] | Daily OCR page limit reached |

## Limitations

- Twilio trial: 50 messages/day (resets midnight UTC = 8am HK)
- Non-ASCII filenames dropped by Twilio — backend sanitizes
- n8n workflow ID: `2KEkDoOvwKB7Y6Ml`

## Connects to

[[Job Queue]] — primary caller
[[Function App]] — alert caller
[[DI Guard]] — alert caller
