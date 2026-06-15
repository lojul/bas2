# Document Processor - Development Rules

## Project Overview
LangGraph + LangSmith document processor. Users drop PDFs in OneDrive `/In`, processed results appear in `/Processed`.

- **Dashboard (production):** Next.js app on Vercel (see Next.js Dashboard section)
- **Backend API:** FastAPI on Azure App Service (see FastAPI Backend section)

## Product Design Philosophy

- **Users never see a terminal** — background service
- **Users interact with OneDrive** — drop files in `/In`, find results in `/Processed`
- **LangSmith is the monitoring UI** — traces, errors, debugging
- **Dashboard Ingest** — users can drop PDF, Word, PowerPoint, JPG, PNG in Admin → Ingest tab; AI triages each file before processing

## Development Rules

### 1. Testing
- Test command: `cd langgraph && source .venv/bin/activate && pytest -v`
- All new nodes must have corresponding tests
- Use mocks for external Azure services in unit tests

### 2. Code Standards
- Python 3.11+, type hints throughout
- Dataclasses for state objects
- `@traceable` decorator on all nodes for LangSmith observability

### 3. Project Structure
```
langgraph/
├── src/
│   ├── nodes/          # Processing nodes
│   │   ├── chatbot.py  # RAG chatbot (production)
│   │   ├── chatbot_v2.py  # LangChain refactored (ready for Phase 2)
│   │   └── report_generator/  # PDF report generation
│   ├── state.py        # DocumentState schema
│   ├── graph.py        # Workflow graph
│   ├── config.py       # Configuration
│   └── utils/
│       ├── json_parser.py     # Shared JSON parsing
│       ├── blob_storage.py    # Azure Blob upload
│       └── table_storage.py   # Azure Table Storage — permanent history log
├── api/
│   ├── main.py         # FastAPI app entry point
│   ├── auth.py         # JWT auth + bcrypt + rate limiting
│   └── routes/
│       ├── chat.py     # /api/chat (stream, report)
│       ├── search.py   # /api/search
│       └── admin.py    # /api/admin (triage, upload, process, vector, history)
├── tests/              # Mirror src structure
├── function_app.py     # Azure Functions (timer + HTTP)
└── .env                # Local secrets (never commit)

nextjs-dashboard/       # Next.js frontend (primary UI)
├── app/
│   ├── (app)/
│   │   ├── chat/       # Chat UI
│   │   ├── search/     # Keyword Search UI
│   │   └── admin/      # Upload / Processing / Vector DB / Settings
│   └── login/
├── components/
│   └── Sidebar.tsx
└── lib/
    └── api.ts          # All API calls (fetch wrapper with JWT)
```

### 4. Sprint Workflow
1. Implement feature
2. Write/update tests
3. Run `pytest -v` to verify
4. Check LangSmith traces for observability
5. Update README progress checklist

### 5. Environment
- Virtual env: `langgraph/.venv`
- Activate: `source .venv/bin/activate`
- Install: `pip install -e ".[dev]"`

### 6. Key Configurations
- LangSmith projects: `document-processor`, `property-chatbot`
- Azure region: Hong Kong / Sweden Central (OpenAI)
- Blob container: `property-pdf`

---

## Current Status
- [x] Project setup & LangSmith tracing
- [x] OneDrive integration (list files, get download URL, move files)
- [x] Azure Document Intelligence OCR
- [x] Folder watcher script (process_inbox.py)
- [x] AI Classification (listing/listing_list/pitching_deck/news/contact) via OpenRouter Qwen
- [x] Streamlit Dashboard (pulls data from LangSmith + Process Now button)
- [x] Data Extraction (structured fields via Qwen 2.5 72B)
- [x] Azure AI Search indexing (vector search with embeddings)
- [x] Azure Functions deployed (timer + HTTP triggers)
- [x] COMPLETE - Full pipeline running in Azure
- [x] RAG Chatbot (Property Intelligence Assistant)
- [x] Streaming responses (real-time answer display)
- [x] Hybrid Search (Vector + Web via Tavily)
- [x] Smart Query Router (vector/web/hybrid based on query type)
- [x] Semantic Ranking (Azure AI Search semantic configuration)
- [x] Pitching Deck support (comprehensive property marketing extraction)
- [x] Document Analysis (pre-extraction structure analysis)
- [x] Smart Index Merge (preserve existing data, don't overwrite with nulls)
- [x] Image Display (extract PDF images, store in blob, display in dashboard)
- [x] Report from Chat Results (generate PDF reports using chatbot search results)
- [x] Multi-Index Search (chatbot searches multiple Azure AI Search indexes)
- [x] Dashboard Upload (upload PDFs directly to OneDrive /In via dashboard)
- [x] Search REST API (external chatbots can query our search via `/api/search`)
- [x] Next.js Dashboard (replaced Streamlit as primary UI; deployed on Vercel)
- [x] FastAPI Backend (Azure App Service; JWT auth + bcrypt + rate limiting)
- [x] Chat "Generate Report PDF" button (Next.js → FastAPI → fpdf2)
- [x] Permanent Processing History (Azure Table Storage — survives LangSmith 14-day expiry)
- [x] Ingest Page with AI Triage (multi-format upload; AI identifies doc type before processing; unsupported files logged)
- [x] JWT sessions extended to 30 days
- [ ] Manual Data Editor (edit extracted_data via form UI in Admin tab)
- [ ] Pipeline support for non-PDF formats (DOCX, PPTX, JPG ingested but pipeline currently OCRs as-is)

---

## Graph 1: Document Processing

**File:** `src/graph.py` | **LangSmith Project:** `document-processor`

### Flow
```
__start__
    ↓
get_download_url (OneDrive via Microsoft Graph)
    ↓
run_ocr (Azure Document Intelligence + PyMuPDF image extraction)
    ↓
classify (OpenRouter Qwen 2.5)
    ↓
analyze (Pre-extraction document structure analysis)
    ↓
extract (OpenRouter Qwen 2.5)
    ↓
index (Azure AI Search + Azure OpenAI embeddings + Smart Merge)
    ↓
__end__
```

### Document Types & Extracted Fields
- **listing**: One property (building_name, address, size, rent, contact)
- **listing_list**: Multiple properties in a table (building info + units array)
- **pitching_deck**: Property marketing presentations (project_summary, available_units, location, key_features, design_team, contact)
- **news**: Article (title, date, source, summary, topics)
- **contact**: Business card (name, company, phone, email)

---

## Key Services

### Azure AI Search
- Endpoint: `aisearch-eastasia-basic.search.windows.net`
- Default Write Index: `processed-documents`
- Read Indexes: `processed-documents,c21net-intelligence-v2` (set via `AZURE_SEARCH_INDEXES`)
- Features: Vector search (text-embedding-3-small, 1536 dims), BM25, hybrid, semantic ranking

#### Multi-Index Search
The chatbot searches ALL indexes in `AZURE_SEARCH_INDEXES`. Writing always goes to `AZURE_SEARCH_INDEX`.

#### Index Schema Differences
| Field | processed-documents | c21net-intelligence-v2 |
|-------|---------------------|------------------------|
| Name | `file_name` | `title` |
| Time | `processed_at` | `last_updated` |
| Data | `extracted_data` | *(built from fields)* |
| Images | `image_urls` | *(not available)* |
| Semantic Config | `default-semantic-config` | `unified-semantic-config` |
| Doc Types | `listing`, `listing_list` | `Vacancy Listing`, `Particular Property` |

### Azure OpenAI
- Endpoint: `swedencentral.api.cognitive.microsoft.com`
- Embedding model: `text-embedding-3-small` (1536 dimensions)

### AI Classification/Extraction
- Provider: OpenRouter — `qwen/qwen-2.5-72b-instruct`
- Temperature: 0 (deterministic)
- Anti-hallucination prompts: return null for missing fields

### OpenRouter Models — Hong Kong

**Working:** `qwen/qwen-2.5-72b-instruct`, `deepseek/deepseek-chat`, `meta-llama/llama-3.3-70b-instruct`, `mistralai/*`

**May not work:** `anthropic/claude-*`, `openai/gpt-*`, `google/gemini-*` (US company regional blocks)

---

## Graph 2: RAG Chatbot

**File:** `src/nodes/chatbot.py` | **LangSmith Project:** `property-chatbot`

### Architecture
```
User Question → route_query → search (vector/web/hybrid) → build_context → call_llm → Answer
```

| Node | Purpose |
|------|---------|
| `route_query` | Determines search strategy |
| `search_documents` | Multi-index hybrid search (Azure AI Search) |
| `web_search` | Tavily web search for trends/news |
| `build_context` | Merges & formats results for LLM |
| `call_llm` | OpenRouter Llama 3.3 70B |

### Query Router
| Route | Keywords |
|-------|----------|
| `vector` | 出租, 寫字樓, office, district names |
| `web` | 趨勢, 市場, 新聞, forecast, 2024/2025/2026 |
| `hybrid` | 比較, compare, versus |

### Configuration
- LLM: `meta-llama/llama-3.3-70b-instruct`, temperature 0.5, max 2000 tokens
- Memory: `MemorySaver` (session-scoped; use `PostgresSaver` for persistent)
- Guardrail: ONLY Hong Kong commercial property questions

### Chatbot v2 (Ready for Phase 2)
`src/nodes/chatbot_v2.py` — LangChain-based refactor (580 lines vs 1,098). Switch when starting Phase 2 (tool-calling agent). Tests pass: 15 passed, 1 skipped.

---

## Report Generator

**Files:** `src/nodes/report_generator/` | Triggered by: Chat tab "生成報告 PDF" button in Next.js dashboard

Uses **chat conversation sources** (not a separate search) to generate PDF reports.

```
router.py → validator.py → aggregator.py → statistics.py → pdf_generator.py → main.py
```

Entry point: `generate_report_from_sources(sources, district, district_en, report_type)`

- Format: A4, professional, C21 branding, bilingual (Chinese + English)
- Types: Rent Analysis, Availability
- Dependencies: `fpdf2` (in requirements.txt), `jinja2`
- `pdf_bytes` is `bytearray` — must cast to `bytes` in FastAPI: `Response(content=bytes(result.report.pdf_bytes), ...)`

**Known issue:** Chinese font may not render correctly in PDF reports (debug `_get_chinese_font()` in `pdf_generator.py`).

---

## Next.js Dashboard (Primary UI)

- **Local:** `cd nextjs-dashboard && npm run dev` → http://localhost:3000
- **Production:** https://c21-property-intelligence.vercel.app/ (Vercel)
- **GitHub:** https://github.com/lojul/c21-document-processor (same repo, `nextjs-dashboard/` subdirectory)
- **Auth:** JWT login via `POST /api/auth/login`; token stored in `localStorage`, sent as `Bearer` on every API call

### Routes
| Route | Label | Notes |
|-------|-------|-------|
| `/chat` | Chat | RAG chatbot, Llama 3.3 70B label, "生成報告 PDF" button |
| `/search` | Keyword Search | Direct keyword search, no AI |
| `/admin/ingest` | Ingest | Drop PDF/Word/PPT/JPG/PNG; AI triages each file then upload to OneDrive /In |
| `/admin/process` | Processing | Two tabs: Recent (LangSmith 72h) + History (Azure Table Storage, all time) |
| `/admin/vector` | Vector DB | Azure AI Search documents |
| `/admin/settings` | Settings | (placeholder) |

### Chat UI Details
- Bilingual (Chinese/English) — responds in same language as query
- Model label: "Llama 3.3 70B" shown dimmed in chat header
- "生成報告 PDF" button: only visible when conversation has listing/listing_list sources
- Uses `allSources` (collected across all completed assistant messages) — not just last response
- Clicking "生成報告 PDF" calls `generateReport(allSources)` → downloads PDF blob

### Deploy
```bash
cd nextjs-dashboard && npx vercel --prod --yes
```
GitHub auto-deploy is configured but use the CLI to force when needed.

### Environment Variables (Vercel)
```
NEXT_PUBLIC_API_URL=https://<azure-app-service-url>
```

---

## FastAPI Backend

- **Local:** `cd langgraph && uvicorn api.main:app --reload`
- **Production:** `https://property-intelligence-api.azurewebsites.net` (Azure App Service Linux, Python 3.11)
- **Deploy dir:** `/private/tmp/api_deploy_dir/` — always sync here before deploying

### Deploy Workflow
```bash
# 1. Sync source files to deploy dir
cd "/Users/kincheonglau/Active Projects/document processor/langgraph"
rsync -a --delete src/ /private/tmp/api_deploy_dir/src/
rsync -a --delete api/ /private/tmp/api_deploy_dir/api/
cp requirements-api.txt /private/tmp/api_deploy_dir/requirements.txt

# 2. Zip (clear pycache first)
cd /private/tmp/api_deploy_dir
find . -name "__pycache__" -exec rm -rf {} + 2>/dev/null
zip -r /private/tmp/api_deploy.zip . -x "*.DS_Store"

# 3. Deploy via Kudu REST API (most reliable — az webapp deploy drops connection)
KUDU_USER='$property-api-c21'
KUDU_PASS='<publishing-password>'  # az webapp deployment list-publishing-credentials
curl -X POST \
  "https://property-api-c21.scm.azurewebsites.net/api/zipdeploy?isAsync=true" \
  -u "$KUDU_USER:$KUDU_PASS" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @/private/tmp/api_deploy.zip

# 4. Poll until status 4 (success)
curl -s -u "$KUDU_USER:$KUDU_PASS" \
  "https://property-api-c21.scm.azurewebsites.net/api/deployments/latest"
```

**Deploy notes:**
- `az webapp deploy` drops connection mid-upload — use Kudu curl instead
- `az webapp deployment source config-zip --build-remote true` flag not available in this CLI version
- Kudu async deploy: status 1 = building, status 4 = success
- `requirements-api.txt` is the canonical dep list for the API; `requirements.txt` is for Azure Functions only

### API Routes
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/auth/login` | None | Get JWT token |
| GET | `/api/health` | None | Health check |
| POST | `/api/chat/stream` | Bearer | SSE streaming chat |
| POST | `/api/chat/report` | Bearer | Generate PDF report |
| POST | `/api/search` | Bearer | Keyword/hybrid search |
| POST | `/api/admin/triage` | Bearer | Quick OCR + classify file before pipeline (single file) |
| POST | `/api/admin/upload` | Bearer | Upload file(s) to OneDrive /In (PDF/DOCX/PPTX/JPG/PNG) |
| GET | `/api/admin/runs` | Bearer | LangSmith runs (last N hours) |
| GET | `/api/admin/history` | Bearer | Permanent history from Azure Table Storage |
| GET | `/api/admin/documents` | Bearer | List indexed documents from Azure Search |

### Authentication & Security (`api/auth.py`)

**JWT:**
- Secret: `JWT_SECRET_KEY` env var. If missing, generates a random key per process — tokens invalidated on restart (acceptable for dev; never uses a known public string).
- Algorithm: HS256, TTL: 720 hours (30 days)

**Passwords (`DASHBOARD_USERS` env var):**
```
# Bcrypt hash (recommended)
DASHBOARD_USERS="admin:$2b$12$..."

# Multiple users
DASHBOARD_USERS="admin:$2b$12$...,user2:$2b$12$..."
```
To generate a hash: `python -c "import bcrypt; print(bcrypt.hashpw(b'PASSWORD', bcrypt.gensalt()).decode())"`

Single-user fallback: `DASHBOARD_ADMIN_PASSWORD` env var (plaintext, legacy).

The code warns when a plaintext password is detected and instructs to migrate to bcrypt.

**Rate limiting:** 5 login attempts per 60 seconds per IP (in-memory `defaultdict`). Returns HTTP 429 on breach.

**IMPORTANT — bcrypt import:** Use `import bcrypt` directly. Do NOT use `passlib` — it is incompatible with newer `bcrypt` versions and throws `MissingBackendError` / "password cannot be longer than 72 bytes".

### Report Endpoint (`POST /api/chat/report`)
```python
# Request body
{ "sources": [...], "district": "中環", "district_en": "Central", "report_type": "rent" }

# Response: application/pdf binary
# Critical: convert bytearray → bytes before returning
return Response(content=bytes(result.report.pdf_bytes), media_type="application/pdf", ...)
```

### CRITICAL: `src/nodes/__init__.py`
Must contain ONLY the docstring:
```python
"""Processing nodes for the document workflow."""
```
Any imports here cause `fitz` (PyMuPDF) to be loaded at startup → Azure App Service crash. The chatbot, report generator, and other nodes import `fitz` transitively; loading them at module init time breaks the API process.

---

## Azure Functions

**File:** `function_app.py`

| Trigger | Schedule/Path | Purpose |
|---------|--------------|---------|
| Timer | every 5 min | Process 7 files per batch from OneDrive /In |
| HTTP POST | `/api/process` | Manual trigger |
| HTTP POST | `/api/search` | External search API (auth: `X-API-Key` header) |

**Production:** `doc-processor-c21.azurewebsites.net` | Resource group: `blob-storage-hk-rg` | Region: East Asia

```bash
# Deploy
func azure functionapp publish doc-processor-c21 --python

# Disable timer
az functionapp config appsettings set --name doc-processor-c21 \
  --resource-group blob-storage-hk-rg \
  --settings "AzureWebJobs.timer_trigger.Disabled=true"
```

### Search REST API (`/api/search`)
```json
POST https://doc-processor-c21.azurewebsites.net/api/search
X-API-Key: <SEARCH_API_KEY>

{ "query": "中環寫字樓出租", "top_k": 5, "search_type": "hybrid" }
```
`search_type`: `hybrid` (default), `keyword`, `vector`

---

## LlamaParse Integration

**Status: Implemented** — `src/nodes/ocr.py`

LlamaParse runs as the **primary text extractor** for all PDFs; Azure Document Intelligence is the **fallback** and still runs for tables, figures, and page count (LlamaParse doesn't return those).

### How it works
```
PDF bytes ──┬── LlamaParse API ──► clean markdown text  (preferred)
            │
            └── Azure Doc Intelligence ──► tables + figures + page count
                                                    │
                                          final_text = llamaparse_text OR azure_text
                                          confidence = 0.98 if llamaparse, else 0.95
```

### Setup
Add to `.env` and Azure App Service settings:
```
LLAMA_CLOUD_API_KEY=llx-...
```
If the key is missing, pipeline silently uses Azure text only — no code changes needed to disable.

### Package
Uses `llama-parse` pip package. The package shows a deprecation warning but the underlying API and functionality remain fully operational.

Free tier: 10,000 credits/month. Monitor at https://cloud.llamaindex.ai/usage

## Ingest & Triage

### Supported Upload Formats
`SUPPORTED_FORMATS = {"pdf", "jpg", "jpeg", "png", "docx", "pptx"}` (defined in `api/routes/admin.py`)

Unsupported formats (e.g. `.xls`, `.doc`, `.ppt`, `.mp4`) are rejected at triage and logged to Azure Table Storage with `status="unsupported"`.

### Triage Endpoint (`POST /api/admin/triage`)
Single-file endpoint called before uploading. Steps:
1. Check extension against `SUPPORTED_FORMATS` — if not supported, log and return `can_process: false`
2. Run Azure DI `prebuilt-read` on first 2 pages (PDFs) or full file (images/docs)
3. Quick LLM classify (`call_openrouter` from `src/nodes/classifier.py`) on first 3000 chars
4. Return `{ file_name, can_process, detected_type, format, confidence, reason }`

Designed to be fast (~3–5s) — only first 2 pages, no full pipeline.

### Azure Table Storage — Processing History
**Account:** `blobhk04472` | **Table:** `ProcessingHistory`
**SAS env var:** `AZURE_TABLE_SAS`

**Functions in `src/utils/table_storage.py`:**
- `log_run(...)` — called by `process_file()` in `graph.py` after every pipeline run
- `log_unsupported(file_name, ext)` — called by triage for unsupported formats
- `list_runs(months, top)` — used by `GET /api/admin/history`

**PartitionKey** = `YYYY-MM` (monthly partitions for fast range queries)
**Status values:** `"success"`, `"error"`, `"unsupported"`

If `AZURE_TABLE_SAS` is not set, all logging silently skips — never crashes the pipeline.

---

## Known Issues

### 409 Conflict on Move to /Processed
**Fix:** `@microsoft.graph.conflictBehavior: replace` in `move_to_processed()` (`src/nodes/onedrive.py`).

### Multi-Index Search Not Working
**Cause:** `AZURE_SEARCH_INDEXES` missing from Azure App Service settings.

### Report Shows 0 Properties
**Cause:** `listing_list` has two formats — `extracted_data.units[]` (old) and `extracted_data.items[].units[]` (new). Statistics module handles both.

### PDF Report Chinese Font
**Problem:** Chinese building names may show as boxes in PDF reports.
**Debug:** Add logging to `_get_chinese_font()` in `pdf_generator.py`.

### Azure App Service Startup Crash (`fitz` / PyMuPDF)
**Problem:** API process crashes at startup with `ImportError` related to `fitz`.
**Cause:** `src/nodes/__init__.py` had imports (`from src.nodes.ocr import ...`) which pulled in PyMuPDF transitively. Azure App Service cannot load the binary extension at import time.
**Fix:** `src/nodes/__init__.py` must contain ONLY `"""Processing nodes for the document workflow."""` — no imports.

### passlib Incompatible with bcrypt ≥ 4.0
**Problem:** `passlib` throws `MissingBackendError` or `ValueError: password cannot be longer than 72 bytes`.
**Fix:** Use `import bcrypt` directly in `api/auth.py`. `passlib` is kept in `requirements.txt` for backward compat but not imported in auth code.

### Report PDF: `bytearray` vs `bytes` in FastAPI
**Problem:** `starlette.responses.Response` calls `.encode()` on content; `bytearray` lacks this method → "Load failed" in browser.
**Fix:** `content=bytes(result.report.pdf_bytes)` in `api/routes/chat.py`.

---

## Planned: Manual Data Editor

**Status:** Not implemented | **Location:** Admin → Vector Database tab → Edit button per document

### Purpose
Allow admins to correct AI-extracted data directly from the dashboard.

### Storage
Edits saved to Azure AI Search `extracted_data` field via merge (preserves unedited fields). Smart merge ensures manual edits survive reprocessing if AI returns null.

### UI Design (Admin → Vector tab)
- "Edit" button per document row → expands form in-place
- **Standard fields** (text/number/dropdown): building_name, address, district, property_type, size_sqft, rent_monthly, floor_unit, contact_name, contact_phone, contact_email
- **Custom fields** section: add/remove arbitrary key-value pairs
- "Save" → PATCH to Azure AI Search, refresh cache

### API for Saving
```python
def update_document_extracted_data(doc_id: str, extracted_data: dict):
    url = f"{SEARCH_ENDPOINT}/indexes/{INDEX}/docs/index?api-version=2024-07-01"
    body = {
        "value": [{
            "@search.action": "merge",
            "id": doc_id,
            "extracted_data": json.dumps(extracted_data, ensure_ascii=False)
        }]
    }
    # POST with api-key header
```

---

## Code Review (2026-06-13)

Principal-grade review was conducted and documented externally:
- **Confluence:** https://c21net.atlassian.net/wiki/x/BAD_AQ ("Document Processor — Code Review, Principal Grade, 2026-06-13")
- **Notion:** https://app.notion.com/p/37eecf49be518179839cd376c418dbf6

Key findings acted on:
1. **JWT secret fallback** — was hardcoded string `"change-me-in-production"`, changed to `secrets.token_hex(32)` per-process random key
2. **Plaintext passwords** — `verify_credentials()` now bcrypt-checks `$2b$`/`$2a$` hashes; plaintext falls back with warning to migrate
3. **No rate limiting on login** — added in-memory per-IP rate limit (5 attempts / 60 sec) via `_check_rate_limit()`

---

## Monthly Costs

| Service | Cost |
|---------|------|
| Vercel (Next.js) | Free (hobby) |
| Azure App Service (FastAPI) | ~$15-20/mo (B1) |
| Azure AI Search | ~$70/mo |
| Azure OpenAI | ~$5-20/mo |
| Azure Functions | ~$0-5/mo |
| OpenRouter (LLM) | ~$1-5/mo |
| Tavily (Web Search) | Free (1k/mo) |
| LangSmith | Free tier |
| **Total** | **~$95-120/mo** |
