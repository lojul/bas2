# Document Processor

Automated document processing pipeline for Hong Kong property documents. Files dropped in OneDrive are automatically OCR'd, classified, and indexed for AI search.

## Architecture

```
User drops PDF in OneDrive
        ↓
Azure Functions (timer every 5 min)
        ↓
LangGraph Pipeline:
  → OneDrive API (get file)
  → Azure Document Intelligence (OCR)
  → DeepSeek (classify)
  → DeepSeek (extract data)
  → Azure AI Search (index + embeddings)
        ↓
File moved to /Processed
        ↓
Streamlit Dashboard (view results)
```

## Technology Stack

### Language
- **Python 3.12**

### Core Framework
| Component | Technology | Purpose |
|-----------|------------|---------|
| LangGraph | Workflow orchestration | Processing pipeline (nodes + edges) |
| LangSmith | Observability | Tracing, monitoring, debugging |

### Azure Services
| Service | Purpose |
|---------|---------|
| Azure Functions | Serverless hosting (timer + HTTP triggers) |
| Azure Document Intelligence | OCR - extracts text from PDFs/images |
| Azure AI Search | Vector database for semantic search |
| Azure OpenAI | Embeddings (`text-embedding-3-small`) |

### Microsoft 365
| Service | Purpose |
|---------|---------|
| OneDrive/SharePoint | File storage (`/In` → `/Processed`) |
| Microsoft Graph API | Access OneDrive files |
| MSAL | Authentication library |

### AI / LLM
| Service | Purpose |
|---------|---------|
| OpenRouter | LLM gateway |
| DeepSeek | Classification + data extraction (Chinese/English) |

### Frontend
| Tool | Purpose |
|------|---------|
| Streamlit | Dashboard UI |

### Libraries
| Library | Purpose |
|---------|---------|
| `httpx` | HTTP client |
| `python-dotenv` | Environment variables |
| `msal` | Microsoft authentication |

## Project Structure

```
langgraph/
├── src/
│   ├── nodes/              # Processing pipeline nodes
│   │   ├── onedrive.py     # OneDrive file operations
│   │   ├── ocr.py          # Azure Document Intelligence
│   │   ├── classifier.py   # Document classification
│   │   ├── extractor.py    # Data extraction
│   │   ├── indexer.py      # Azure AI Search indexing
│   │   └── chatbot.py      # RAG chatbot with memory
│   ├── utils/
│   │   └── json_parser.py  # Shared JSON parsing
│   ├── graph.py            # LangGraph workflow definition
│   ├── state.py            # State schema (dataclasses)
│   └── config.py           # Configuration management
├── tests/                  # Unit tests
├── scripts/                # Utility scripts
├── dashboard.py            # Streamlit dashboard (3 tabs)
├── function_app.py         # Azure Functions entry point
├── langgraph.json          # LangGraph Studio config
└── requirements.txt        # Dependencies
```

## Graph Flow

```
__start__ → get_download_url → run_ocr → classify → extract → index → __end__
```

## Document Types

| Type | Description | Extracted Fields |
|------|-------------|------------------|
| `listing` | Single property | building_name, address, size, rent, contact |
| `listing_list` | Multiple properties | building info + units array |
| `news` | Market article | title, date, source, summary, topics |
| `contact` | Business card | name, company, phone, email |

## Setup

### 1. Install Dependencies

```bash
cd langgraph
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Configure Environment

Create `.env` file with:

```env
# Azure Document Intelligence
AZURE_DOC_INTEL_KEY=xxx
AZURE_DOC_INTEL_ENDPOINT=https://xxx.cognitiveservices.azure.com

# Azure AI Search
AZURE_SEARCH_ENDPOINT=https://xxx.search.windows.net
AZURE_SEARCH_API_KEY=xxx
AZURE_SEARCH_INDEX=processed-documents

# Azure OpenAI (for embeddings)
AZURE_OPENAI_ENDPOINT=https://xxx.openai.azure.com
AZURE_OPENAI_KEY=xxx

# OpenRouter (for LLM)
OPENROUTER_API_KEY=xxx

# Microsoft Graph (OneDrive)
MS_GRAPH_CLIENT_ID=xxx
MS_GRAPH_TENANT_ID=xxx
MS_GRAPH_CLIENT_SECRET=xxx
MS_GRAPH_DRIVE_ID=xxx

# LangSmith
LANGCHAIN_API_KEY=xxx
LANGCHAIN_PROJECT=document-processor
LANGCHAIN_TRACING_V2=true
```

### 3. Run Dashboard

```bash
streamlit run dashboard.py
```

### 4. Deploy to Azure

```bash
func azure functionapp publish doc-processor-c21 --python
```

## Development

### Run Tests

```bash
pytest -v
```

### LangGraph Studio

```bash
langgraph dev
```

Opens visual debugger at `http://localhost:8123`

## Azure Functions

| Trigger | Schedule | Batch Size |
|---------|----------|------------|
| Timer | Every 5 minutes | 7 files |
| HTTP | On-demand | 7 files |

### Endpoints

- `POST /api/process` - Manual trigger
- `GET /api/health` - Health check

### Control Timer

```bash
# Disable auto-processing
az functionapp config appsettings set --name doc-processor-c21 \
  --resource-group blob-storage-hk-rg \
  --settings "AzureWebJobs.timer_trigger.Disabled=true"

# Re-enable
az functionapp config appsettings delete --name doc-processor-c21 \
  --resource-group blob-storage-hk-rg \
  --setting-names "AzureWebJobs.timer_trigger.Disabled"
```

## OneDrive Workflow

```
/Document Processor/In        ← Drop files here
/Document Processor/Processed ← Completed files moved here
```

- Supports subfolders (recursive scan)
- File types: `.pdf`, `.jpg`, `.jpeg`, `.png`
- Files with same name are replaced in `/Processed`

## Monitoring

- **LangSmith**: Real-time traces at [smith.langchain.com](https://smith.langchain.com)
- **Dashboard**: Processing status + Vector DB at `http://localhost:8501`

## RAG Chatbot

Property Intelligence Assistant with conversation memory.

### Features
- **Streaming Responses**: See answer as it generates in real-time
- **Bilingual**: Traditional Chinese / English (auto-detects)
- **Property Search**: Find offices, retail, industrial units
- **Recommendations**: Suggests properties based on criteria
- **Market Analysis**: Compare rents, identify trends
- **Source Citations**: Shows which documents were used
- **Conversation Memory**: Remembers context via LangGraph Checkpointing
- **Scope Restriction**: Only answers property-related questions

### Architecture
```
User Question
     ↓
Vector Search (Azure AI Search)
     ↓
Build Context (top 5 documents)
     ↓
LLM (Llama 3.3 70B via OpenRouter)
     ↓
Answer with Sources
```

### LangSmith Projects
| Project | Purpose |
|---------|---------|
| `document-processor` | File processing traces |
| `property-chatbot` | Chat conversation traces |

### Memory System
- **LangGraph Checkpointing** with `MemorySaver`
- Each session gets unique `thread_id`
- Conversation persists within session
- "Clear" button resets memory (new thread)

## Dashboard

Three-tab Streamlit interface at `http://localhost:8501`

| Tab | Purpose |
|-----|---------|
| Processing Status | Real-time LangSmith traces, file status |
| Vector Database | Azure AI Search indexed documents |
| Chat | Property Intelligence chatbot |

### Chat Interface
- Input at **top**, newest messages near input
- Reversed message order (newest first)
- Source documents expandable
- Session-based conversation memory

## Cost

| Service | Tier | Cost |
|---------|------|------|
| Azure Functions | Consumption | Free (1M exec/month) |
| Azure AI Search | Basic | ~$70/month |
| Azure OpenAI | Pay-per-use | ~$0.02/1M tokens |
| Azure Doc Intelligence | F0 | Free (500 pages/month) |
| OpenRouter (DeepSeek) | Pay-per-use | ~$0.001/request |
| OpenRouter (Llama 3.3) | Pay-per-use | ~$0.001/request |
| LangGraph | Open source | Free |
| Streamlit | Local/Cloud | Free |

## Completed Features

- [x] OneDrive integration (recursive folder scan)
- [x] Azure Document Intelligence OCR
- [x] AI Classification (listing/listing_list/news/contact)
- [x] Data Extraction (structured fields via DeepSeek)
- [x] Azure AI Search indexing (vector + embeddings)
- [x] Azure Functions (timer + HTTP triggers)
- [x] Streamlit Dashboard (3 tabs)
- [x] RAG Chatbot with vector search
- [x] Conversation memory (LangGraph Checkpointing)
- [x] Bilingual support (Chinese/English)
- [x] Scope restriction (property-only answers)
- [x] Separate LangSmith projects
- [x] Streaming responses (real-time answer display)

## Future Improvements

### Document Processor
| Improvement | Description | Priority |
|-------------|-------------|----------|
| Hybrid Search | Combine keyword + vector search for better recall | High |
| Batch Embeddings | Process multiple documents in single embedding call | Medium |
| Retry Logic | Exponential backoff for transient API failures | Medium |
| Duplicate Detection | Skip files already processed (hash-based) | Medium |
| PDF Page Splitting | Index individual pages for granular search | Low |
| Webhook Trigger | Real-time processing on file upload (vs polling) | Low |

### RAG Chatbot
| Improvement | Description | Priority |
|-------------|-------------|----------|
| Persistent Memory | PostgresSaver for cross-session memory | High |
| ~~Streaming Responses~~ | ~~Show answer as it generates~~ | ✅ Done |
| Re-ranking | Use cross-encoder to improve retrieval quality | Medium |
| Query Expansion | Rephrase query for better vector matching | Medium |
| Multi-turn Retrieval | Re-search on follow-up questions | Medium |
| Agent Tools | Let LLM call search/filter tools directly | Low |
| Feedback Loop | Thumbs up/down to improve responses | Low |

### Dashboard
| Improvement | Description | Priority |
|-------------|-------------|----------|
| Cloud Deployment | Streamlit Community Cloud with OAuth | High |
| Real-time Updates | WebSocket for live processing status | Medium |
| Export Function | Download search results as CSV/Excel | Low |
| Analytics | Processing trends, popular queries | Low |
