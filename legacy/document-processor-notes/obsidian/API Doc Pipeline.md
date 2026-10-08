# API Doc Pipeline

**File:** `langgraph/api/doc_pipeline_main.py`
**URL:** `https://c21net-bas-api-doc-pipeline-ea-prod.azurewebsites.net`

## Routes

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/login` | JWT login |
| GET | `/api/health` | Health check |
| POST | `/api/admin/triage` | Quick OCR + classify before full pipeline |
| POST | `/api/admin/upload` | Upload file to OneDrive /In |
| GET | `/api/admin/runs` | LangSmith traces (last N hours) |
| GET | `/api/admin/history` | [[Azure Table Storage]] permanent history |
| GET | `/api/admin/documents` | [[Azure AI Search]] document list |
| POST | `/api/assistant/message` | [[Assistant]] entry point (WhatsApp + dashboard) |

## Deploy

```bash
cd langgraph && ./deploy.sh        # doc-pipeline only
cd langgraph && ./deploy.sh --all  # everything
```

## Connects to

[[Assistant]] — hosts it
[[Pipeline]] — triage runs partial pipeline
[[API Prop Chat]] — shares same codebase, different entrypoint
[[Azure Table Storage]] — history log
[[Azure AI Search]] — document list
