# Azure Table Storage

**Account:** `blobhk04472` (same account as [[Azure Blob Storage]])

## Tables

| Table | Purpose | Used by |
|---|---|---|
| `ProcessingHistory` | Permanent run log (survives LangSmith 14-day expiry) | [[API Doc Pipeline]] history tab |
| `DiUsage` | Daily DI page count | [[DI Guard]] |
| Sessions table | Assistant conversation state | [[Assistant]] |

## ProcessingHistory schema

- **PartitionKey**: `YYYY-MM` (monthly, fast range queries)
- **RowKey**: timestamp + file_name
- **Status**: `"success"` · `"error"` · `"unsupported"`

## Env var

```
AZURE_TABLE_SAS=...
```

Silently skips all logging if not set — never crashes the pipeline.

## Connects to

[[DI Guard]] — DiUsage table
[[API Doc Pipeline]] — history endpoint reads ProcessingHistory
[[Assistant]] — session storage
[[Pipeline]] — logs every run
