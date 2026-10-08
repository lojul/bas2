# Odoo Sync

**File:** `langgraph/src/nodes/odoo_sync.py`
**Protocol:** XML-RPC

## Two roles

1. **Pipeline node** — after [[Indexer]], syncs extracted data to Odoo `x_c21_listing` model
2. **Assistant tool** — `query_odoo_listings` searches active Odoo records by keyword/district

## Pipeline sync logic

```
listing / listing_list / pitching_deck → x_c21_listing records
news → Odoo Knowledge articles (via knowledge_writer.py)
contact / unknown → skipped
```

For `listing_list`: one Odoo record per unit (not per file).

## query_odoo_listings domain logic

```python
# When keyword given: search all statuses, correct OR prefix notation
["|", ["x_name", "ilike", keyword], ["x_c21_address", "ilike", keyword]]

# When district only: filter active records
[["x_c21_status", "=", "active"], ["x_c21_district", "=", district_key]]
```

Bug history: `|` was inserted at position 0 instead of before the two OR conditions — caused `(status OR name) AND address` logic that never matched. Fixed 2026-07-08.

## Connects to

[[Pipeline]] — called as the `odoo_sync` node
[[State]] — reads `extracted`, writes `odoo_record_id` / `odoo_sync_status`
[[Assistant]] — `query_odoo_listings` tool
