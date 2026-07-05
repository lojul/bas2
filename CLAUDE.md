# Document Processor - Development Rules

## Project Overview
LangGraph + LangSmith document processor. Users drop PDFs in OneDrive `/In`, processed results appear in `/Processed`.

- **Dashboard (production):** Next.js app on Azure Static Web Apps (see Next.js Dashboard section)
- **Backend API:** FastAPI on Azure App Service (see FastAPI Backend section)
- **Document pipeline:** Azure Function App timer trigger (see Azure Functions section)

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
│   │   └── report_generator/  # PDF report generation
│   ├── state.py        # DocumentState schema
│   ├── graph.py        # Workflow graph
│   ├── config.py       # Configuration
│   └── utils/
│       ├── json_parser.py     # Shared JSON parsing
│       ├── blob_storage.py    # Azure Blob upload
│       ├── table_storage.py   # Azure Table Storage — permanent history log
│       ├── job_queue.py       # Durable pipeline job queue (enqueue + worker + notify)
│       ├── file_cache.py      # Blob-backed pending-file cache (WhatsApp confirmations)
│       ├── di_guard.py        # Document Intelligence daily cost guard
│       ├── whatsapp_notify.py # WhatsApp send via n8n notify webhook
│       └── session_storage.py # Assistant session persistence (Table Storage)
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
- [x] Next.js Dashboard (replaced Streamlit as primary UI; deployed on Azure Static Web Apps)
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
- **LLM resilience (2026-07-05):** all pipeline LLM calls (classify/analyze/extract) go through
  `openrouter_chat()` in `src/utils/llm.py` — Qwen, retry once after 2s, then fall back to
  `deepseek/deepseek-chat`. Added after OpenRouter failed 3 ways in 2 days (502/504/400) and
  single blips degraded runs to UNKNOWN. Do NOT add raw `httpx.post` OpenRouter calls in nodes.
- **Extraction memory Phase 1 (2026-07-05):** `fetch_examples()` in extractor.py retrieves the
  2 most similar past extractions (same document_type) from Azure AI Search and injects them as
  few-shot examples before extracting. Fails open. Quality compounds as good extractions accumulate.
- **Listing names (2026-07-05):** extractor captures `listing_ref` (樓盤編號) + `headline`;
  `_build_listing_name()` in odoo_sync.py enriches short/generic names → "中環 商舖 #10978"
  instead of "中環". Teaser ads (IG/WhatsApp promos) often carry no address.

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

### Chatbot v2 — REMOVED (2026-07-05)
`chatbot_v2.py` was deleted. It was a June refactor preparing for a tool-calling agent, but the
WhatsApp assistant (`src/nodes/assistant.py`) already IS that agent, and v2 lacked multi-index
search. If dashboard chat should become agentic, expose the existing assistant
(`channel="dashboard"` is already supported) — do not rebuild a parallel chatbot.

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
- **Production:** https://wonderful-flower-006019c00.7.azurestaticapps.net/ (Azure Static Web Apps — free tier)
- **GitHub:** https://github.com/lojul/property-intelligence-dashboard (separate repo, `main` branch)
- **Deploy:** Push to `main` → GitHub Actions auto-builds and deploys (workflow: `.github/workflows/azure-static-web-apps-wonderful-flower-006019c00.yml`)
- **Build env vars:** `NEXT_PUBLIC_API_URL` set in the workflow file (build-time, not runtime)
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
cd nextjs-dashboard
npm run build   # outputs ./out (static export)
SWA_TOKEN=$(az staticwebapp secrets list \
  --name c21net-bas-web-prop-intel-dashboard-ea-prod \
  --resource-group c21net-bas-document-processor-ea-prod \
  --query "properties.apiKey" -o tsv)
npx @azure/static-web-apps-cli deploy ./out \
  --deployment-token "$SWA_TOKEN" --env production
```

### Environment Variables
Set at build time in `nextjs-dashboard/.env.local` (not committed):
```
NEXT_PUBLIC_PIPELINE_API_URL=https://c21net-bas-api-doc-pipeline-ea-prod.azurewebsites.net
NEXT_PUBLIC_CHAT_API_URL=https://c21net-bas-api-prop-chat-ea-prod.azurewebsites.net
```

---

## FastAPI Backend (Split into Two Services)

The monolithic API is split into two named App Services:

| Service | Entrypoint | URL | Routes |
|---------|-----------|-----|--------|
| `c21net-bas-api-doc-pipeline-ea-prod` | `api/doc_pipeline_main.py` | `https://c21net-bas-api-doc-pipeline-ea-prod.azurewebsites.net` | pipeline, admin, billing, monitoring |
| `c21net-bas-api-prop-chat-ea-prod` | `api/prop_chat_main.py` | `https://c21net-bas-api-prop-chat-ea-prod.azurewebsites.net` | chat, search |

- **Resource group:** `c21net-bas-document-processor-ea-prod` | **Subscription:** `c21net-business-automation-stack`
- Old monolith `c21net-bas-api-prop-intel-core-ea-prod` was deleted (verified gone 2026-07-05)
- **App Service Plan:** `c21net-bas-asp-ea-prod` (B1, Linux, Python 3.12)
- **Deploy dir:** `/private/tmp/api_deploy_dir/` — staged files live here; do NOT clean between deploys

### Deploy Workflow — USE `./deploy.sh` (added 2026-07-04)

```bash
cd langgraph
./deploy.sh          # doc-pipeline App Service
./deploy.sh --chat   # + prop-chat App Service
./deploy.sh --func   # + Function App
./deploy.sh --all    # everything
```

The script does the full sequence with built-in guards: stage → zip (size + freshness checks) →
zipdeploy → wait for the NEW deployment id (avoids race with the previous deploy) → copy source
to wwwroot → restart → health poll. Do NOT hand-run the steps below anymore — manual deploys
caused stale-zip incidents twice on 2026-07-04.

**Function App:** `.funcignore` (excludes `.venv/`, `tests/`, etc.) is REQUIRED. Without it,
`func publish` uploads ~918MB and silently deploys stale code.

### Manual steps (reference only — what deploy.sh automates)

`az webapp deploy --type zip` and `az webapp deployment source config-zip` both drop the connection. Use the Kudu REST API directly:

```bash
# 1. Sync source files to deploy dir (--delete removes stale files)
cd "/Users/kincheonglau/Active Projects/document processor/langgraph"
rsync -a --delete src/ /private/tmp/api_deploy_dir/src/
rsync -a --delete api/ /private/tmp/api_deploy_dir/api/
cp requirements-api.txt /private/tmp/api_deploy_dir/requirements.txt

# 2. Clean pycache and zip — IMPORTANT: separate rm and zip, do NOT chain with &&
cd /private/tmp/api_deploy_dir
find . -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
rm -f /private/tmp/api-deploy.zip
zip -r /private/tmp/api-deploy.zip . -x "*.DS_Store"

# 3. Verify new entrypoints are in the zip before deploying
unzip -l /private/tmp/api-deploy.zip | grep -E "doc_pipeline|prop_chat|requirements.txt"

# 4. Get bearer token
TOKEN=$(az account get-access-token --resource "https://management.azure.com/" --query accessToken -o tsv)

# 5. Deploy to Pipeline API
# IMPORTANT: --http1.1 is required. Without it, HTTP/2 framing causes connection drop (HTTP 000).
curl --http1.1 -X POST \
  "https://c21net-bas-api-doc-pipeline-ea-prod.scm.azurewebsites.net/api/zipdeploy?isAsync=true" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @/private/tmp/api-deploy.zip
# Expect HTTP 202 (accepted).

# 6. Deploy to Chat API (same zip — both services run from same codebase)
curl --http1.1 -X POST \
  "https://c21net-bas-api-prop-chat-ea-prod.scm.azurewebsites.net/api/zipdeploy?isAsync=true" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @/private/tmp/api-deploy.zip

# 7. Poll deploy status (~5 min for Oryx build)
TOKEN=$(az account get-access-token --resource "https://management.azure.com/" --query accessToken -o tsv)
for svc in c21net-bas-api-doc-pipeline-ea-prod c21net-bas-api-prop-chat-ea-prod; do
  echo "=== $svc ===" && \
  curl -s "https://${svc}.scm.azurewebsites.net/api/deployments" \
    -H "Authorization: Bearer $TOKEN" | python3 -c "
import json,sys
deps=json.load(sys.stdin)
for d in deps[:1]:
    print(d['id'][:16],'status:',d['status'],'complete:',d['complete'],d.get('status_text',''))
"
done

# 8. CRITICAL: Copy source files into wwwroot after Oryx build
# Oryx extracts zip to /tmp/zipdeploy/extracted/ and only puts the virtualenv in output.tar.zst.
# wwwroot keeps old source files unless explicitly overwritten. Must do this after every deploy.
TOKEN=$(az account get-access-token --resource "https://management.azure.com/" --query accessToken -o tsv)
for svc in c21net-bas-api-doc-pipeline-ea-prod c21net-bas-api-prop-chat-ea-prod; do
  echo "Copying source to $svc wwwroot..."
  curl -s -X POST "https://${svc}.scm.azurewebsites.net/api/command" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"command": "python3 -c \"import subprocess; r1=subprocess.run([chr(115)+chr(104),chr(45)+chr(99),chr(99)+chr(112)+chr(32)+chr(45)+chr(114)+chr(102)+chr(32)+chr(47)+chr(116)+chr(109)+chr(112)+chr(47)+chr(122)+chr(105)+chr(112)+chr(100)+chr(101)+chr(112)+chr(108)+chr(111)+chr(121)+chr(47)+chr(101)+chr(120)+chr(116)+chr(114)+chr(97)+chr(99)+chr(116)+chr(101)+chr(100)+chr(47)+chr(115)+chr(114)+chr(99)+chr(32)+chr(47)+chr(104)+chr(111)+chr(109)+chr(101)+chr(47)+chr(115)+chr(105)+chr(116)+chr(101)+chr(47)+chr(119)+chr(119)+chr(119)+chr(114)+chr(111)+chr(111)+chr(116)+chr(47)], capture_output=True, text=True); r2=subprocess.run([chr(115)+chr(104),chr(45)+chr(99),chr(99)+chr(112)+chr(32)+chr(45)+chr(114)+chr(102)+chr(32)+chr(47)+chr(116)+chr(109)+chr(112)+chr(47)+chr(122)+chr(105)+chr(112)+chr(100)+chr(101)+chr(112)+chr(108)+chr(111)+chr(121)+chr(47)+chr(101)+chr(120)+chr(116)+chr(114)+chr(97)+chr(99)+chr(116)+chr(101)+chr(100)+chr(47)+chr(97)+chr(112)+chr(105)+chr(32)+chr(47)+chr(104)+chr(111)+chr(109)+chr(101)+chr(47)+chr(115)+chr(105)+chr(116)+chr(101)+chr(47)+chr(119)+chr(119)+chr(119)+chr(114)+chr(111)+chr(111)+chr(116)+chr(47)], capture_output=True, text=True); print(r1.returncode, r2.returncode)\"", "dir": "/"}'
done

# 9. Restart both services so Python picks up the new source files
az webapp restart --name c21net-bas-api-doc-pipeline-ea-prod --resource-group c21net-bas-document-processor-ea-prod
az webapp restart --name c21net-bas-api-prop-chat-ea-prod --resource-group c21net-bas-document-processor-ea-prod

# 10. Verify health endpoints (wait ~30s after restart)
curl https://c21net-bas-api-doc-pipeline-ea-prod.azurewebsites.net/api/health
curl https://c21net-bas-api-prop-chat-ea-prod.azurewebsites.net/api/health
```

**Deploy notes:**
- Oryx build takes ~5 min; site starts ~2 min after build
- `requirements-api.txt` is the canonical dep list; it must be copied as `requirements.txt` at zip root — Oryx ignores all other names
- Do NOT use `az webapp deploy --type zip` or `az webapp deployment source config-zip` — both fail with connection drop on az CLI 2.84.0
- **MUST add `--http1.1` to curl zipdeploy** — HTTP/2 causes connection close (returns HTTP 000); `--http1.1` forces HTTP/1.1 and gets HTTP 202 correctly
- Both App Services share the same zip — the startup command determines which entrypoint runs
- Token expires after ~1 hour; refresh with `az account get-access-token` if deploy takes long
- **ZIP PITFALL:** Always run `rm -f /private/tmp/api-deploy.zip` as a SEPARATE command (not chained with `&&` after a command that might fail). `zip -r` in update mode silently reuses old content if the file already exists.
- **SOURCE FILES PITFALL:** Oryx extracts the zip to `/tmp/zipdeploy/extracted/` (temp), NOT to wwwroot. Oryx only puts the built virtualenv into `output.tar.zst` in wwwroot. Source files in wwwroot are NEVER updated by the deploy — only the virtualenv is. After every deploy, you MUST manually copy `/tmp/zipdeploy/extracted/src/` and `/tmp/zipdeploy/extracted/api/` to wwwroot via the Kudu command API (step 8 above), then restart both services (step 9).
- **`SCM_DO_BUILD_DURING_DEPLOYMENT=true` REQUIRED** — If set to false, Kudu extracts the zip but Oryx does NOT install packages. The app crashes with "No module named uvicorn". This must be `true` on both services or every deploy wipes the virtualenv.

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

| Trigger | Schedule | Purpose |
|---------|----------|---------|
| Timer | every 5 min | Process 7 files per batch from OneDrive /In + poison-queue watchdog |
| Queue | `pipeline-jobs` | Durable pipeline job worker (WhatsApp/dashboard dispatch) |
| HTTP GET | `/api/health` | Health check (anonymous) |

**Production:** `c21net-bas-func-doc-pipeline-ea-prod.azurewebsites.net`
**Resource group:** `c21net-bas-document-processor-ea-prod` | **Subscription:** `c21net-business-automation-stack`

```bash
# Deploy (set subscription first — func CLI doesn't support --subscription)
az account set --subscription "c21net-business-automation-stack"
cd langgraph
func azure functionapp publish c21net-bas-func-doc-pipeline-ea-prod --python

# Disable timer
az functionapp config appsettings set --name c21net-bas-func-doc-pipeline-ea-prod \
  --resource-group c21net-bas-document-processor-ea-prod \
  --subscription "c21net-business-automation-stack" \
  --settings "AzureWebJobs.timer_trigger.Disabled=true"
```


## WhatsApp Assistant (added 2026-07-04)

**Principle: channels are media only.** WhatsApp, dashboard, and OneDrive all feed the same
pipeline codeline (`process_file_from_bytes` / `graph.py`). Never build channel-specific
processing paths.

### Flow
```
WhatsApp user → Twilio → n8n "WhatsApp Twilio Integration" (2KEkDoOvwKB7Y6Ml)
  → n8n sends ⏳ ack, downloads media (Twilio Basic Auth)
  → POST /api/assistant/message (X-Api-Key = ASSISTANT_API_KEY)
  → assistant fast paths or ReAct agent (src/nodes/assistant.py)
  → job enqueued to Storage Queue "pipeline-jobs"
  → Function App pipeline_job_worker runs the full pipeline
  → completion notification via n8n "WhatsApp Notify" webhook → Twilio → user
```

### Assistant fast paths (no LLM — instant reply, avoids OpenRouter 502/504 flakiness)
- Greeting/menu words → instant menu
- Image, no text → dup check → auto-dispatch (pipeline classifier decides news vs listing)
- PDF/other, no text → ask 知識文章 or 物業盤源
- File + listing trigger ("3"/"物業盤源"/"yes"...) in one message → dispatch immediately
- File + text ≥60 chars → forwarded post: the TEXT becomes the document content
  (`precomputed_ocr`, skips Azure DI), image kept for Odoo attachment
- "yes" after news duplicate warning → force-dispatch (checked BEFORE listing triggers)
- Anything else → ReAct agent (Qwen via OpenRouter) with tools: create_knowledge_article,
  process_property_listing, check_listing_duplicate, search_properties, query_odoo_listings

### Durable job queue
- `src/utils/job_queue.py`: `enqueue_pipeline_job()` (App Service) + `run_pipeline_job()`
  (Function App queue trigger). File bytes staged in blob container `pipeline-jobs`.
- Survives App Service restarts; 5 retries then poison queue; timer alerts ADMIN_WHATSAPP
  if poison queue is non-empty (`check_poison_queue`).
- Thread fallback if queue unavailable. Completion formatting lives in job_queue.py
  (NOT assistant.py — Function App must not import langchain).
- Pending-file cache is blob-backed: `src/utils/file_cache.py`, container
  `assistant-file-cache`, 30-min TTL — "3"/"yes" confirmations survive restarts.

### Known limitations
- **Twilio drops non-ASCII filenames** (Chinese → `?`). Backend sanitizes: strips `?`,
  falls back to `document-{timestamp}` if <3 chars remain. Chinese filenames only survive
  via dashboard uploads.
- **Twilio trial: 50 messages/day** — resets midnight UTC (8am HK). Upgrade removes cap.
- n8n passes `file_name_override` form field (UTF-8 text) because Node.js encodes binary
  Content-Disposition headers as Latin-1.
- **Forwarded posts sometimes arrive without caption text** (Twilio Body empty) — the image-OCR
  path handles them; DI reads the flyer content directly.
- **Job-blob cleanup gets 403** — AZURE_BLOB_WRITE_SAS lacks delete permission, so processed
  job files linger in `pipeline-jobs` container. Harmless; fix by regenerating SAS with `d` perm.

### DI cost guard (`src/utils/di_guard.py`)
- Counts OCR pages in Table Storage (table `DiUsage`), checked BEFORE every DI call
- Hard-stops past `DI_DAILY_PAGE_LIMIT` (default 200/day); WhatsApps `ADMIN_WHATSAPP` on trip
- Fails open if Table Storage unavailable; covers this codeline only (not the separate ETL project)

### Env vars added 2026-07-04
| Setting | Where | Purpose |
|---------|-------|---------|
| `ASSISTANT_API_KEY` | both + n8n | Auth for /api/assistant/message + notify webhook |
| `N8N_NOTIFY_WEBHOOK_URL` | both | n8n WhatsApp Notify webhook |
| `PIPELINE_QUEUE_CONN` | App Service | Storage conn string for pipeline-jobs queue (same account as Function App AzureWebJobsStorage) |
| `ADMIN_WHATSAPP` | both | Admin number for guard/poison alerts |
| `DI_DAILY_PAGE_LIMIT` | both (optional) | OCR daily page ceiling, default 200 |
| `AZURE_BLOB_READ_SAS`, `AZURE_TABLE_SAS`, `ODOO_API_KEY` | Function App | Were missing/stale — queue worker needs them |

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

## Known Issues & Fixes Backlog

### 🔴 1. `processed-documents` Index is Empty
**Problem:** 0 docs in `processed-documents` on new search service (`c21net-bas-aisearch-ea-prod`). Chatbot and Search tab only find docs from `c21net-intelligence-v2` (771 docs). ~124 old docs were never reprocessed after migration.

**Fix:** Drop the old 124 docs back into OneDrive `/Document Processor/In` — timer will pick them up and reindex into `processed-documents`.

---

### 🟡 2. Double OCR on Manual Upload
**Problem:** When using the Ingest tab, Azure Document Intelligence is called twice for the same file:
- `POST /api/pipeline/triage` → DI on first 2 pages
- `POST /api/pipeline/process` → DI on ALL pages again

Two DI transactions per manual upload — unnecessary cost.

**Fix:** In `api/routes/pipeline.py`, pass the triage OCR result (text + page_count) as part of the process request body, and skip the DI call in `process_file()` if OCR text is already provided. Store triage result in browser state between triage and process steps.

**Files to change:**
- `api/routes/pipeline.py` → `process_file()` — accept optional pre-computed OCR text
- `app/(app)/admin/ingest/page.tsx` → pass triage OCR result when calling `processIngest()`
- `lib/api.ts` → update `processIngest()` signature

---

### 🟡 3. `MOVE_WHEN_DONE=false` on Timer
**Problem:** After the timer processes a file from OneDrive `/In`, it stays there. Nothing moves it to `/Processed`. Risk of reprocessing on next timer run.

**Verify first:** Check that `function_app.py` skips files already indexed in Azure AI Search before reprocessing. If skip logic exists and works → low risk, leave as-is. If not → reprocessing will happen every 5 min.

**Fix (option A):** Set `MOVE_WHEN_DONE=true` in Function App env vars:
```bash
az functionapp config appsettings set \
  --name c21net-bas-func-doc-pipeline-ea-prod \
  --resource-group c21net-bas-document-processor-ea-prod \
  --subscription "c21net-business-automation-stack" \
  --settings "MOVE_WHEN_DONE=true"
```
**Fix (option B):** Confirm skip-if-indexed logic in `function_app.py` and keep as-is.

---

### 🟡 4. `blobhk04472` Still on Old Subscription
**Problem:** All blob storage (PDFs, images) and Table Storage (ProcessingHistory) live on old subscription (`Azure subscription 1` / `blob-storage-hk-rg`). Split billing — if old subscription lapses, everything breaks.

**Fix:** Full storage migration:
1. Create new storage account in `c21net-bas-document-processor-ea-prod`
2. Copy `property-pdf` blob container contents (azcopy)
3. Copy `ProcessingHistory` table (azcopy or script)
4. Copy `document-images` blob container
5. Generate new SAS tokens
6. Update env vars on both Function App and API:
   - `AZURE_BLOB_ACCOUNT`
   - `AZURE_BLOB_WRITE_SAS`
   - `AZURE_TABLE_SAS`
   - `AZURE_BLOB_CONTAINER`
   - `AZURE_BLOB_IMAGES_CONTAINER`

---

### 🟢 5. Function App and API Share B1 Plan
**Problem:** `c21net-bas-asp-ea-prod` (B1, 1 core, 1.75GB RAM) runs both the Function App and the API. Heavy batch processing (7 PDFs) while users are on chatbot → both slow down.

**Fix:** Upgrade plan to B2, or move Function App to a Consumption plan (pay-per-execution, scales independently):
```bash
# Option A: upgrade shared plan to B2
az appservice plan update \
  --name c21net-bas-asp-ea-prod \
  --resource-group c21net-bas-document-processor-ea-prod \
  --subscription "c21net-business-automation-stack" \
  --sku B2
```
**Note:** Only needed if performance becomes an issue. Fine for current traffic.

---

### 🟢 6. No Error Boundaries in Next.js
**Problem:** If an API call throws an unhandled error, the whole page crashes with a blank screen. No fallback UI shown to the user.

**Fix:** Add `error.tsx` files next to each `page.tsx` in the App Router — Next.js automatically uses these as error boundaries:
- `app/(app)/chat/error.tsx`
- `app/(app)/admin/ingest/error.tsx`
- `app/(app)/admin/process/error.tsx`
- `app/(app)/admin/vector/error.tsx`

```tsx
// error.tsx pattern
"use client";
export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="p-6 text-red-500">
      <p>Something went wrong: {error.message}</p>
      <button onClick={reset}>Try again</button>
    </div>
  );
}
```

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
| Azure Static Web Apps (Next.js) | Free tier |
| Azure App Service (FastAPI) | ~$15-20/mo (B1) |
| Azure AI Search | ~$70/mo |
| Azure OpenAI | ~$5-20/mo |
| Azure Functions | ~$0-5/mo |
| OpenRouter (LLM) | ~$1-5/mo |
| Tavily (Web Search) | Free (1k/mo) |
| LangSmith | Free tier |
| **Total** | **~$95-120/mo** |

---

## Extraction Memory (AI Self-Improvement)

**Status:** Phase 1 LIVE (2026-07-05) · Phases 2–3 planned

The system learns from past successful extractions rather than processing every document cold.

### Phase 1 — Few-shot Extraction Memory ✅ IMPLEMENTED
**File:** `src/nodes/extractor.py` — `fetch_examples(text_sample, doc_type)`

Before extraction, keyword-searches `processed-documents` for the top 2 past extractions of the
same document_type and prepends them to the prompt as reference examples (with an instruction
not to copy values). Fails open on any error. Skips docs with `_extraction_failed`.

### Phase 2 — Correction Learning (Human-in-the-loop)
**Depends on:** Manual Data Editor being built first

When an admin corrects extracted data via the Manual Editor, mark that document as a gold standard example — weight it higher in Phase 1 retrieval.

**Changes:**
- `src/nodes/indexer.py` — add `is_example` (bool) and `example_weight` (int) fields to index schema
- `api/routes/admin.py` — `PATCH /documents/{id}` already exists; add `is_example` flag support
- `app/(app)/admin/ingest/page.tsx` — "Mark as example" button after successful processing

### Phase 3 — Self-Improving Prompts
**File:** New background task or admin endpoint

Periodically analyse failed/weak extractions (many null fields, low confidence) and suggest prompt improvements for human review.

**Changes:**
- New script or `GET /api/admin/prompt-suggestions` endpoint
- Queries Azure Table Storage for runs with high null-field rate
- Sends patterns to gpt-5-mini → returns suggested prompt edits
- Admin reviews and applies to `PROMPTS` dict in `src/nodes/extractor.py`

### Data Already Available (No Migration Needed)
- Past extracted data → `processed-documents` index, `extracted_data` field
- Vector embeddings → `content_vector` field (1536 dims, already indexed)
- Run history → Azure Table Storage `ProcessingHistory`
- Manual corrections → Manual Data Editor (once built)
