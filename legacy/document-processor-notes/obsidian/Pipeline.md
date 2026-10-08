# Pipeline

**File:** `langgraph/src/graph.py`
**LangSmith project:** `document-processor`

## Flow

```
__start__
   ↓
[[OneDrive]] (get_download_url)
   ↓
[[OCR]] (Azure Document Intelligence + PyMuPDF)
   ↓
[[Classifier]] (OpenRouter Qwen 2.5 72B)
   ↓
[[Analyzer]] (regex structure scan)
   ↓
[[Extractor]] (OpenRouter Qwen 2.5 72B + few-shot memory)
   ↓
[[Indexer]] (Azure AI Search + Azure OpenAI embeddings)
   ↓
[[Odoo Sync]] (XML-RPC)
   ↓
__end__
```

## Entry points

| Caller | Function | Source field |
|---|---|---|
| [[Function App]] timer | `process_file()` | `"onedrive"` |
| [[Job Queue]] worker | `process_file_from_bytes()` | `"assistant"` |
| [[API Doc Pipeline]] triage | `process_file_from_bytes()` | `"dashboard"` |

## State

All nodes read and write [[State]] (`DocumentState`). Errors set `status=ERROR` and stop the graph.

## LLM resilience

All LLM calls go through `openrouter_chat()` in `src/utils/llm.py`:
- Primary: Qwen 2.5 72B
- Retry after 2s on failure
- Fallback: DeepSeek Chat
