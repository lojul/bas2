# Document Processor — System Overview

## Two entry points, one pipeline

```
WhatsApp user ──→ [[Assistant]] ──→ [[Job Queue]] ──→ [[Pipeline]]
Dashboard user ──→ [[API]] ──────────────────────────→ [[Pipeline]]
OneDrive timer ──────────────────────────────────────→ [[Pipeline]]
```

## The pipeline always produces the same result

[[State]] flows through every node in order:

[[OneDrive]] → [[OCR]] → [[Classifier]] → [[Analyzer]] → [[Extractor]] → [[Indexer]] → [[Odoo Sync]]

## Where data lives

| Data | Store |
|---|---|
| Indexed documents | [[Azure AI Search]] |
| Source PDFs | [[Azure Blob Storage]] |
| Processing history | [[Azure Table Storage]] |
| Pending WhatsApp files | [[Azure Blob Storage]] |
| Sessions | [[Azure Table Storage]] |

## Two deployed services + one function app

- [[API Doc Pipeline]] — admin, upload, triage, pipeline trigger
- [[API Prop Chat]] — chat, search
- [[Function App]] — timer (OneDrive), queue worker (WhatsApp jobs)

## Key principle

> Channels are media only. WhatsApp, dashboard, and OneDrive all run the **same** [[Pipeline]]. Never build channel-specific logic.
