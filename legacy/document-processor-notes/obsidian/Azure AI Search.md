# Azure AI Search

**Service:** `c21net-bas-aisearch-ea-prod`
**Endpoint:** `aisearch-eastasia-basic.search.windows.net`
**Tier:** Basic (supports semantic ranking)

## Indexes

| Index | Writer | Reader | Notes |
|---|---|---|---|
| `processed-documents` | [[Indexer]] | [[Search]], [[Assistant]] | Everything run through [[Pipeline]] |
| `c21net-intelligence-v2` | ETL project | [[Search]], [[Assistant]] | Legacy 771-doc dataset |

## Key fields (processed-documents)

`id` · `file_name` · `document_type` · `content` · `content_vector` · `extracted_data` (JSON string) · `image_urls` · `processed_at` · `sell_price` · `return_rate` · `transaction_type` · `extraction_path` · `needs_review` · `odoo_record_id` · `odoo_sync_status` · `source_url` · `whatsapp_number`

## Search modes

- **Vector**: cosine similarity on `content_vector` (1536-dim, `text-embedding-3-small`)
- **Keyword**: BM25 on `content`, `file_name`
- **Hybrid**: vector + keyword combined
- **Semantic reranker**: Microsoft ML re-ranker, scores 0-4, config `default-semantic-config`

## Env vars

```
AZURE_SEARCH_ENDPOINT
AZURE_SEARCH_API_KEY
AZURE_SEARCH_INDEX=processed-documents        # write target
AZURE_SEARCH_INDEXES=processed-documents,c21net-intelligence-v2  # read targets
```

## Connects to

[[Indexer]] — writes documents
[[Search]] — reads documents
[[Extractor]] — few-shot examples fetched from here
