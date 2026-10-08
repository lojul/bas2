# State

**File:** `langgraph/src/state.py`
**Class:** `DocumentState`

## The single object that flows through every pipeline node

```python
DocumentState
├── file_path          # OneDrive item ID (empty for direct uploads)
├── file_name          # Display name
├── source             # "onedrive" | "dashboard" | "assistant"
├── whatsapp_number    # Sender's E.164 number (WhatsApp jobs only)
├── file_bytes         # Raw bytes (cleared after OCR)
│
├── status             # ProcessingStatus enum
├── error_message      # Set on failure
│
├── blob_url           # OneDrive download URL
├── ocr                # OCRResult (text, tables, figures, image_urls)
│
├── document_type      # DocumentType enum
├── classification_confidence
│
├── analysis           # Pre-extraction structure scan
├── extraction_path    # "structured" | "conversational" | "visual"
├── extracted          # ExtractedData (raw dict + field_confidence)
├── needs_review       # Low-confidence flag
│
├── index_id           # MD5(file_name) — Azure Search doc ID
├── chunks_indexed
│
├── odoo_record_id     # Odoo record ID(s) after sync
├── odoo_sync_status   # "synced" | "duplicate" | "skipped" | "error"
├── odoo_doc_url       # Odoo Documents shareable URL
└── skip_duplicate_check
```

## Document types

`listing` · `listing_list` · `pitching_deck` · `news` · `contact` · `unknown`

## Connects to

Every node in [[Pipeline]] reads and writes this object.
[[Indexer]] persists it to [[Azure AI Search]].
[[Odoo Sync]] uses it to create/update Odoo records.
[[Job Queue]] carries `whatsapp_number` and `source` through the queue payload.
