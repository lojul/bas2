# Document Processor - Development Rules

## Project Overview
LangGraph + LangSmith document processor running in parallel with n8n workflow.

## Product Design Philosophy

### User-Friendly First
- **Users will never see a terminal** - this is a background service
- **Users only interact with OneDrive** - drop files in `/In`, find results in `/Processed`
- **LangSmith is the monitoring UI** - all traces, errors, and debugging happen there
- **No technical knowledge required** - clients just drop files and get results

### OneDrive Workflow
```
/Document Processor/In        ← Client drops files here
/Document Processor/Processed ← System moves completed files here
```

## Development Rules

### 1. Testing
- **Always run tests** before marking a sprint complete
- Test command: `cd langgraph && source .venv/bin/activate && pytest -v`
- All new nodes must have corresponding tests
- Use mocks for external Azure services in unit tests

### 2. Code Standards
- Python 3.11+
- Use type hints throughout
- Dataclasses for state objects
- `@traceable` decorator on all nodes for LangSmith observability
- Keep functions small and focused

### 3. Project Structure
```
langgraph/
├── src/           # Source code
│   ├── nodes/     # Processing nodes
│   ├── state.py   # State schema
│   ├── graph.py   # Workflow graph
│   └── config.py  # Configuration
├── tests/         # Test files (mirror src structure)
└── .env           # Local secrets (never commit)
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
- LangSmith projects:
  - `document-processor` - Document processing pipeline logs
  - `property-chatbot` - Chatbot conversation logs
- Azure region: Hong Kong / Sweden Central (OpenAI)
- Blob container: `property-pdf`

## Current Status
- [x] Project setup & LangSmith tracing
- [x] OneDrive integration (list files, get download URL, move files)
- [x] Azure Document Intelligence OCR
- [x] Folder watcher script (process_inbox.py)
- [x] AI Classification (listing/listing_list/news/contact) via OpenRouter
- [x] Streamlit Dashboard (pulls data from LangSmith + Process Now button)
- [x] Data Extraction (structured fields via DeepSeek AI)
- [x] Azure AI Search indexing (vector search with embeddings)
- [x] Azure Functions deployed (timer + HTTP triggers)
- [x] COMPLETE - Full pipeline running in Azure
- [x] RAG Chatbot (Property Intelligence Assistant)
- [x] Streaming responses (real-time answer display)
- [x] Phase 1: Hybrid Search (Vector + Web via Tavily)
- [x] Smart Query Router (vector/web/hybrid based on query type)
- [x] Multi-query retrieval (bilingual query variations)
- [x] LLM reranking (DeepSeek relevance scoring)
- [x] Parallel execution (ThreadPoolExecutor)
- [x] Token usage tracking in dashboard
- [x] PDF Report Generator (Rent Analysis, Availability reports with images)

## Graph Flow
```
__start__ → get_download_url → run_ocr → classify → extract → index → __end__
```

## Document Types & Extracted Fields
- **Single Listing** (`listing`): One property per file (building_name, address, size, rent, contact)
- **Multi Listing** (`listing_list`): Multiple properties in a table (building info + units array)
- **News** (`news`): Article (title, date, source, summary, topics)
- **Contact** (`contact`): Business card (name, company, phone, email)

## Key Services

### Azure AI Search
- Endpoint: `aisearch-eastasia-basic.search.windows.net`
- Index: `processed-documents`
- Features: Vector search with embeddings

### Azure OpenAI
- Endpoint: `swedencentral.api.cognitive.microsoft.com`
- Embedding model: `text-embedding-3-small` (1536 dimensions)

### AI Classification/Extraction
- Provider: OpenRouter
- Model: `deepseek/deepseek-chat`

### Tavily Web Search
- API: `tavily.com`
- Used for: Market trends, news, real-time information
- Integrated in chatbot hybrid search
- Free tier: 1,000 searches/month

### AI Classification/Extraction Notes
- Good for Chinese/English documents
- Classifier uses Hong Kong property keywords (樓盤編號, 已吉, 招租, 成交, etc.)
- Auto-detection logic for listing_list (multiple properties) and contact (short text with email/phone)

## RAG Chatbot

### Architecture (Hybrid Search)
```
User Question → Route Query → Search(es) → Build Context → LLM → Answer
     ↓              ↓            ↓              ↓           ↓
  thread_id    vector/web/   Azure AI      Combined    Llama 3.3
               hybrid        + Tavily      context       70B
```

### Query Router
Smart routing based on query keywords:
| Route | Keywords | Example |
|-------|----------|---------|
| `vector` | 出租, 寫字樓, district names | "中環有什麼寫字樓出租" |
| `web` | 趨勢, 市場, 新聞, forecast | "香港商業地產市場趨勢" |
| `hybrid` | 比較, compare | "比較中環租金同市場走勢" |

### Configuration
- Provider: OpenRouter
- Model: `meta-llama/llama-3.3-70b-instruct`
- LangSmith project: `property-chatbot`
- Vector index: `processed-documents` (same as document processor)
- Web search: Tavily API

### Features
- **Hybrid Search**: Combines vector DB (documents) + web search (Tavily)
- **Smart Routing**: Auto-selects search method based on query type
- **Non-Streaming**: Reliable responses (streaming caused timeout issues)
- **Semantic Ranking**: Azure AI Search semantic configuration for relevance
- **Bilingual**: Auto-detects Traditional Chinese / English
- **Property Search**: Find offices, retail, industrial units
- **Recommendations**: Suggests properties based on criteria
- **Market Analysis**: Compare rents, identify trends (uses web search)
- **Source Citations**: Shows documents (📄) and web results (🌐)
- **Scope Restriction**: ONLY answers property-related questions

### Conversation Memory
- Uses **LangGraph Checkpointing** with `MemorySaver`
- Each session gets unique `thread_id` stored in `st.session_state`
- Memory persists within session (follow-up questions work)
- "Clear" button resets memory (generates new thread_id)
- For persistent memory across sessions, use `PostgresSaver`

### Key Files
- `src/nodes/chatbot.py` - RAG implementation with LangGraph
- `dashboard.py` - Chat tab UI with memory integration

### System Prompt Guardrails
The chatbot ONLY answers Hong Kong commercial property questions:
- Property listings, leasing, recommendations, market analysis
- Declines off-topic questions (cooking, coding, travel, etc.)
- Redirects user to property-related queries

---

## Report Generator

**Files:** `langgraph/src/nodes/report_generator/`
**Triggered via:** Chatbot (natural language commands)

### How to Use

```
User: "Generate rent report for Central"
User: "幫我生成中環租金報告"
User: "Create availability report for Kwun Tong"
```

### Available Report Types

| Type | ID | Description |
|------|-----|-------------|
| Rent Analysis | `rent` | Average rent, price/sqft, building comparison |
| Availability | `availability` | Vacant units, sizes, contacts |
| Market Overview | `market` | Trends, news, inventory (Phase 2) |
| Development Pipeline | `pipeline` | New projects, GFA (Phase 2) |
| Contact Directory | `contacts` | Agent/broker contacts (Phase 2) |

### Supported Districts

**Hong Kong Island:** 中環, 金鐘, 灣仔, 銅鑼灣, 北角, 鰂魚涌, 上環, 黃竹坑
**Kowloon:** 尖沙咀, 旺角, 九龍灣, 觀塘, 紅磡, 長沙灣
**New Territories:** 荃灣, 葵涌, 沙田, 大埔, 元朗, 屯門

### Architecture

```
User Request
     ↓
detect_report_intent() → Is this a report request?
     ↓
parse_report_request() → Extract district, type
     ↓
validate_request() → Missing params? Ask user
     ↓
aggregate_documents() → Fetch from Azure Search
     ↓
compute_statistics() → Python calculations (no LLM)
     ↓
generate_pdf_report() → Jinja2 + WeasyPrint
     ↓
upload_pdf_to_blob() → Azure Blob Storage
     ↓
Return download link to user
```

### Module Structure

```
src/nodes/report_generator/
├── __init__.py
├── router.py           # Intent detection, parameter parsing
├── validator.py        # Validate params, prompt for missing
├── aggregator.py       # Fetch docs from Azure Search
├── statistics.py       # Compute stats (Python, no LLM)
├── pdf_generator.py    # WeasyPrint PDF generation
├── main.py             # Main orchestrator
├── templates/
│   ├── rent_analysis.html
│   └── availability_analysis.html
└── assets/
    └── c21_logo.png
```

### PDF Output

- **Format:** A4, professional layout with C21 branding
- **Sections:** Header, Stats cards, Building analysis table, Property listings, Images grid
- **Bilingual:** Chinese and English labels
- **Images:** Up to 9 property images in 3x3 grid

### Dependencies

Pure Python - no system dependencies required:
```
pip install jinja2 fpdf2
```

Works on: Azure Functions, Streamlit Cloud, any Python environment.

### Integration with Chatbot

The report generator is integrated into the chatbot's `route_query()` function:
- Query containing report keywords → routes to "report"
- `retrieve_node` calls `handle_report_request()`
- If params missing, returns prompt asking for more info
- If complete, generates PDF and returns download link

---

## Dashboard
- URL: `http://localhost:8501`
- Production: `https://c21-document-processing.streamlit.app/`
- Data source: LangSmith (real-time) + Azure AI Search (vector DB) + Tavily (web)
- Timezone: HKT (GMT+8)
- Theme: Light (configured in `~/.streamlit/config.toml`)
- Run: `streamlit run dashboard.py`
- Current Version: v17

### Tab Order (Search is default)
1. **Search** - Direct keyword search with semantic ranking + image display
2. **Chat** - Property Intelligence Assistant (RAG chatbot) + image display
3. **Document Process** - LangSmith traces, file status
4. **Vector** - Azure AI Search indexed documents + image display

### Search Tab Features
- Simple search input + button (no filters)
- Semantic ranking with reranker score filtering (threshold: 2.5)
- Results show: building, address, district, size, rent, type
- Contact details: name, title, phone 📞, email ✉️
- Summary: First 250 chars of document content
- **Image gallery**: Expandable thumbnails for documents with images
- Responsive styling with proper margins

### Chat Tab Features
- Non-streaming for reliability (avoids timeout issues)
- Clear button uses callback (properly clears input + messages)
- Hybrid search: vector + web (Tavily)
- Source citations with expandable details
- **Image display**: Thumbnails in sources expander (max 3 per source)

### Document Process Tab
- LangSmith traces, file status, pagination
- Grouped by filename (no duplicate rows), sorted newest first
- Status: OK, ERR, Fixed (reprocessed), x2/x3 (run count)
- View button to expand extracted data

### Vector Tab
- Azure AI Search indexed documents
- Filter by document type
- Display names: "Single Listing" / "Multi Listing" (internal: listing/listing_list)

## Code Structure

### Shared Utilities
- `src/utils/json_parser.py` - Shared JSON parsing for AI responses
  - Handles markdown code blocks, trailing commas, partial JSON
  - Used by classifier and extractor

### Node Functions
All node functions have:
- `@traceable` decorator for LangSmith observability
- Type hints
- Proper error handling (distinguishes API errors vs parse errors)

### Performance Optimizations
- Reusable HTTP client in `indexer.py` (avoids creating new connections per call)
- Single-pass stats calculation in dashboard
- Text truncation done once, not redundantly

## Azure Functions Deployment

### Files
- `function_app.py` - Main entry point (timer + HTTP triggers)
- `host.json` - Azure Functions config
- `requirements.txt` - Python dependencies
- `local.settings.json` - Local dev settings

### Triggers
- **Timer**: Every 5 minutes (`0 */5 * * * *`) - processes 7 files per batch
- **HTTP**: `POST /api/process` for manual trigger
- Files moved to `/Processed` after successful processing

### Production Settings
- Function App: `doc-processor-c21`
- Resource Group: `blob-storage-hk-rg`
- Region: East Asia
- Batch Size: 7 files per run (to avoid timeout)
- URL: `https://doc-processor-c21.azurewebsites.net`

### Control Timer Trigger
```bash
# Disable timer (manual only)
az functionapp config appsettings set --name doc-processor-c21 \
  --resource-group blob-storage-hk-rg \
  --settings "AzureWebJobs.timer_trigger.Disabled=true"

# Enable timer (auto-processing)
az functionapp config appsettings delete --name doc-processor-c21 \
  --resource-group blob-storage-hk-rg \
  --setting-names "AzureWebJobs.timer_trigger.Disabled"
```

### Deploy Commands
```bash
# Deploy to Azure
cd langgraph
func azure functionapp publish doc-processor-c21 --python

# Check logs
az monitor app-insights query --app doc-processor-c21 \
  --resource-group blob-storage-hk-rg \
  --analytics-query "traces | where timestamp > ago(30m) | project timestamp, message | order by timestamp desc | take 20"
```

## Known Issues & Fixes

### 409 Conflict on Move to /Processed
**Problem:** Files fail to move from /In to /Processed with 409 Conflict error when a file with the same name already exists.

**Fix:** Added `@microsoft.graph.conflictBehavior: replace` to `move_to_processed()` in `src/nodes/onedrive.py`. This overwrites existing files instead of failing.

**Symptoms:** Files stuck in /In, timer reprocessing same files repeatedly, dashboard showing x9/x10 run counts.

### Dashboard Tabs
Using `st.tabs()` for navigation between Processing Status and Vector Database views. Multi-page apps with `pages/` folder had issues with Streamlit version.

### LangSmith Run Deletion Not Supported
**Problem:** LangSmith API doesn't support deleting individual runs (DELETE returns 405 Method Not Allowed).

**Note:** Dashboard no longer has hide/delete functionality. Runs are permanent in LangSmith.

### View Button Performance
Using View button in each row. Data expands below the row when clicked.

### LangSmith API Limits
- Maximum 100 runs per query (400 error if exceeded)
- Cache TTL: 30 seconds
- Incomplete runs (no outputs) are filtered from cache to avoid stale "Unknown" types

### Dashboard Data Sorting
Runs are sorted by time (newest first) before grouping by filename. When grouping, if a run has "unknown" type but another run for the same file has valid data, the valid data is used.

### Streamlit Theme
Light theme configured in `~/.streamlit/config.toml`:
```toml
[theme]
base = "light"
```

### PDF Report Chinese Font (NOT WORKING)
**Problem:** Chinese building names show as "N/A" in PDF reports.

**Current State:**
- Chinese font (WenQuanYi Micro Hei, 4.9MB) uploaded to Azure Blob: `https://blobhk04472.blob.core.windows.net/fonts/wqy-microhei.ttc`
- Code attempts to download and cache font at runtime
- Font works locally but NOT on Streamlit Cloud

**Possible Issues:**
1. Font download may be failing on Streamlit Cloud (network/timeout)
2. The data in Azure Search may not have Chinese names (extraction issue)
3. Font caching path may differ on Streamlit Cloud

**Debug Steps for Next Time:**
1. Add logging to `_get_chinese_font()` in `pdf_generator.py`
2. Check if font download succeeds on Streamlit Cloud
3. Verify Azure Search data contains Chinese building names
4. Test with smaller font file or different font format

**Files:**
- `src/nodes/report_generator/pdf_generator.py` - Font download logic
- Font URL: `CHINESE_FONT_URL` constant

## Streamlit Cloud Deployment

### Production URL
- **URL**: https://c21-document-processing.streamlit.app/
- **GitHub Repo**: https://github.com/lojul/c21-document-processor (private)

### Authentication
- **Method**: Username/Password only (OAuth removed)
- **Credentials**: Stored in Streamlit Cloud secrets under `[passwords]`
- **Login**: Centered responsive form

### Secrets Configuration
Secrets are stored in Streamlit Cloud (Settings → Secrets), NOT in code.

Required secrets:
```toml
# API Keys (MUST be at root level, BEFORE any [section])
TAVILY_API_KEY = "..."
LANGCHAIN_API_KEY = "..."
LANGCHAIN_PROJECT = "document-processor"
AZURE_SEARCH_ENDPOINT = "..."
AZURE_SEARCH_API_KEY = "..."
AZURE_SEARCH_INDEX = "processed-documents"
AZURE_OPENAI_ENDPOINT = "..."
AZURE_OPENAI_KEY = "..."
OPENROUTER_API_KEY = "..."
AZURE_FUNCTION_URL = "..."

# Authentication (sections MUST come after root-level keys)
[passwords]
admin = "your-password-here"
```

**Important:** In TOML format, once you declare a `[section]`, all subsequent keys belong to that section. Always put API keys at the TOP before any `[section]` headers.

### Deployment Workflow
1. Push to GitHub: `git push origin master`
2. Streamlit Cloud auto-deploys on push
3. Manual reboot: Streamlit dashboard → App settings → Reboot

### Local Development
- Auth is skipped when secrets are not configured
- Set `STREAMLIT_LOCAL_DEV=true` to explicitly skip auth
- Run: `streamlit run dashboard.py`

### Monthly Costs
| Service | Cost |
|---------|------|
| Streamlit Cloud | Free |
| Azure AI Search | ~$70/mo |
| Azure OpenAI | ~$5-20/mo |
| Azure Functions | ~$0-5/mo |
| OpenRouter (LLM) | ~$1-5/mo |
| Tavily (Web Search) | Free (1k/mo) |
| LangSmith | Free tier |
| **Total** | **~$80-100/mo** |

## Roadmap

### Completed
- [x] Phase 1: Hybrid Search + Advanced RAG
  - Hybrid search (Vector + Web via Tavily)
  - Multi-query retrieval (bilingual query variations)
  - LLM reranking (DeepSeek relevance scoring)
  - Parallel execution (ThreadPoolExecutor)
  - Token usage tracking in dashboard

### Planned
- [ ] Phase 2: Tool-Calling Agent (LangChain)
  - PDF report generation
  - PPT presentation creation
  - Email with attachments

### Potential Improvements (LangSmith/LangGraph)

| Priority | Feature | Status | Effort | Benefit |
|----------|---------|--------|--------|---------|
| 1 | PostgresSaver | Not started | 2 hours | Persistent memory across sessions |
| 2 | LangSmith Evaluations | Not started | 1 day | Automated RAG quality testing |
| 3 | Online Monitoring | Not started | 4 hours | Real-time quality scoring |
| 4 | Human-in-the-Loop | Not started | 1 day | Approval workflows for Phase 2 |

#### PostgresSaver - Persistent Memory
- Current: `MemorySaver` resets when app restarts
- Improvement: `PostgresSaver` persists conversations forever
- Users can continue conversations days later
- Requires PostgreSQL database

#### LangSmith Evaluations - RAG Quality Testing
- Create test dataset with expected Q&A pairs
- Automated evaluators: relevance, groundedness
- Run on every PR via pytest integration
- Catch regressions before deploy

#### Online Monitoring - Production Quality
- Score every production response automatically
- Track quality trends over time
- Detect issues early via alerts

#### Human-in-the-Loop - Approval Workflows
- Agent pauses for human approval before actions
- Useful for Phase 2: email sending, file generation
- LangGraph checkpointer enables pause/resume

### Future Integrations (Researched)
- [ ] Slack Bot Integration (Socket Mode or Azure Functions)
  - Uses Slack Bolt Python SDK
  - Can reuse existing chatbot.py

### Refactored Chatbot (Ready for Phase 2)

**Files:**
```
src/nodes/chatbot.py        # Current production (1,098 lines)
src/nodes/chatbot_backup.py # Backup of original
src/nodes/chatbot_v2.py     # LangChain refactored (580 lines, 47% smaller)
tests/test_chatbot_v2.py    # Test suite for v2
```

**What chatbot_v2.py uses:**
- LangChain `ChatOpenAI` for LLM calls (simpler streaming)
- LangChain messages (`HumanMessage`, `AIMessage`, `SystemMessage`)
- Same embeddings from `indexer.py` (Azure OpenAI)
- Same LangGraph + MemorySaver for conversation memory

**When to switch to v2:**
- When starting Phase 2 (tool-calling agent)
- LangChain agents work better with LangChain LLM instances
- v2 provides cleaner base for adding tools

**How to switch:**
```bash
# Backup current
cp src/nodes/chatbot.py src/nodes/chatbot_v1_production.py

# Switch to v2
cp src/nodes/chatbot_v2.py src/nodes/chatbot.py

# Run tests
python tests/run_chatbot_tests.py

# Deploy
git add . && git commit -m "Switch to LangChain-based chatbot" && git push
```

**v2 test status:** 15 passed, 1 skipped (TAVILY_API_KEY optional)
