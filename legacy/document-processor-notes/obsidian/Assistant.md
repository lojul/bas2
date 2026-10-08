# Assistant

**File:** `langgraph/src/nodes/assistant.py`
**Model:** [[Azure OpenAI]] `gpt-5-mini` (Sweden Central) — swapped 2026-07-08 from Llama 3.3 70B

## Role

Channel-agnostic ReAct agent. Handles WhatsApp and dashboard chat. Decides which tool to call based on user intent — never hardcoded routing.

## Flow

```
User message
   ↓
_resolve_language() — detect from current message (or walk back through session history for short replies)
   ↓
Inject MANDATORY LANGUAGE OVERRIDE at top of system prompt
   ↓
Fast-path checks (greeting, image-only, "yes" confirmation)
   ↓ (if not fast-pathed)
LangGraph ReAct loop
   ├── search_properties → [[Search]]     ← auto-logs CRM lead on specific building match
   ├── find_similar_properties → [[Search]]
   ├── contact_staff → [[WhatsApp Notify]] (fire-and-forget to Julian)
   ├── log_property_inquiry → [[Odoo Sync]]
   ├── create_crm_lead → [[Odoo Sync]]
   ├── query_odoo_listings → [[Odoo Sync]]
   ├── process_property_listing → [[Job Queue]]
   └── create_knowledge_article → [[Job Queue]]
   ↓
Reply to user
```

## Tools (9 total, added 2026-07-08)

| Tool | Purpose | Notes |
|---|---|---|
| `search_properties` | Vector + keyword search | Returns JSON. Auto-logs CRM lead for specific building queries. |
| `find_similar_properties` | Alternatives by district / size / budget | Called after thin search results |
| `contact_staff` | Redirect to Julian Lau | Fire-and-forget WhatsApp notify + wa.me link |
| `log_property_inquiry` | 1-tap CRM using WhatsApp # | No name/phone asked from user |
| `create_crm_lead` | Full lead creation | Only when logging DIFFERENT client's inquiry |
| `query_odoo_listings` | Odoo records lookup | Only when user explicitly asks about Odoo |
| `process_property_listing` | Full pipeline for attached PDF/image | Enqueues to [[Job Queue]] |
| `create_knowledge_article` | Save news/market content | Enqueues to [[Job Queue]] |
| `check_listing_duplicate` | Duplicate check by filename | Direct Azure Search query |

## Language handling

`_detect_language()` counts CJK vs ASCII letters in the current message. Short replies (`"2"`, `"yes"`, emoji) return `None` → `_resolve_language()` walks back through session history for the most recent user message with alphabetic content. Injected as `MANDATORY LANGUAGE OVERRIDE` at the TOP of the system prompt so it beats history.

## Removed 2026-07-08

- **Hidden fast path** (formerly ~60 lines) that bypassed the LLM for any message containing HK district or search keywords. Returned hardcoded Chinese. This is why prompt fixes weren't working. Never re-add.
- **Auto-CRM offer in system prompt** — replaced by silent `_auto_log_inquiry` call inside `search_properties`.

## Env vars

```
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_KEY
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-5-mini    # or gpt-5.4 for max quality
STAFF_WHATSAPP=+85293072432                # Julian Lau
STAFF_NAME=Julian Lau
```

## Connects to

[[Job Queue]] — dispatches pipeline jobs
[[Search]] — property lookups
[[Odoo Sync]] — CRM leads + Odoo listings query
[[WhatsApp Notify]] — completion messages + staff notifications
[[Session Storage]] — conversation memory
[[File Cache]] — pending file between messages
[[Azure OpenAI]] — LLM backend
