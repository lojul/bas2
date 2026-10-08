# DI Guard

**File:** `langgraph/src/utils/di_guard.py`
**Azure Table:** `DiUsage` (in [[Azure Table Storage]])

## Purpose

Prevent runaway Azure Document Intelligence costs. The $4,012 incident (2026-07-03) happened because a backfill loop ran DI on thousands of pages with no limit.

## How it works

Before every DI call in [[OCR]]:
1. Count today's pages in `DiUsage` table
2. If count ≥ `DI_DAILY_PAGE_LIMIT` (default 200): block the call, alert `ADMIN_WHATSAPP`
3. After successful DI call: log page count to table
4. Fails open if Table Storage unavailable

## Connects to

[[OCR]] — checks before every call
[[Azure Table Storage]] — reads/writes usage counts
[[WhatsApp Notify]] — alerts admin on trip
