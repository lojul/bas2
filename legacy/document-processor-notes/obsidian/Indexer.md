# Indexer

**File:** `langgraph/src/nodes/indexer.py`

## What it does

Takes the final [[State]] after extraction and upserts it into [[Azure AI Search]].

## Steps

1. Hash `file_name` → `doc_id` (MD5)
2. Fetch existing document (carry over `odoo_record_id` if present)
3. Truncate OCR text to 8,000 chars
4. Enrich content with `sell_price` / `return_rate` for BM25 searchability
5. Get embedding from Azure OpenAI (`text-embedding-3-small`)
6. Build doc dict including `whatsapp_number` from state
7. Upload with `@search.action: upload`

## Smart merge (REMOVED 2026-07-05)

Previously merged new extraction with existing data to avoid overwriting good data with nulls. Removed — now always uses fresh extraction. Past data survives via the few-shot memory in [[Extractor]].

## Key fields written

See [[Azure AI Search]] for full schema.

## Connects to

[[Pipeline]] — called as the `index` node
[[State]] — reads from it
[[Azure AI Search]] — writes to it
[[Extractor]] — few-shot examples come back from the index
