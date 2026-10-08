# Azure Blob Storage

**Account:** `blobhk04472` (⚠️ still on old subscription — migration planned)

## Containers

| Container | Purpose | Used by |
|---|---|---|
| `property-pdf` | Source PDFs from OneDrive | [[OCR]], [[Indexer]] |
| `document-images` | Images extracted from PDFs | [[OCR]], dashboard |
| `pipeline-jobs` | Staged file bytes for [[Job Queue]] | [[Job Queue]], [[Function App]] |
| `assistant-file-cache` | Pending WhatsApp files (30-min TTL) | [[Assistant]] |
| `fonts` | Chinese font for PDF reports | Report generator |
| `config` | `settings.json` runtime config | [[API Doc Pipeline]], [[Function App]] |

## Env vars

```
AZURE_BLOB_ACCOUNT=blobhk04472
AZURE_BLOB_WRITE_SAS=...   # needs rwc permissions (lacks d = can't delete job blobs)
AZURE_BLOB_READ_SAS=...
AZURE_BLOB_CONTAINER=property-pdf
AZURE_BLOB_IMAGES_CONTAINER=document-images
```

## Known issues

- `AZURE_BLOB_WRITE_SAS` lacks delete (`d`) permission — processed job blobs linger in `pipeline-jobs`
- Account is on old subscription (`Azure subscription 1`) — if it lapses, everything breaks
- Migration to `c21net-bas-document-processor-ea-prod` subscription is planned but not done

## Connects to

[[Job Queue]] — file staging
[[OCR]] — image extraction
[[Indexer]] — image URLs
[[Assistant]] — file cache
[[DI Guard]] — (via [[Azure Table Storage]] on same account)
