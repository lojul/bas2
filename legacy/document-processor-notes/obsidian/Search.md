# Search

**File:** `langgraph/src/nodes/chatbot.py`
**LangSmith project:** `property-chatbot`

## Two search consumers

```
[[Assistant]] tool → search_properties() → search_documents()
Dashboard /search → keyword_search()
```

## search_documents() — hybrid multi-index

1. Get query embedding (Azure OpenAI `text-embedding-3-small`)
2. For EACH index in `AZURE_SEARCH_INDEXES`:
   - Vector search on `content_vector`
   - Keyword search on `content`, `file_name` (if hybrid=True)
3. Deduplicate by `file_name` then by `building_name`
4. Sort by semantic reranker score
5. Return top_k

## Indexes searched

| Index | Contains |
|---|---|
| `processed-documents` | Everything run through [[Pipeline]] |
| `c21net-intelligence-v2` | Legacy 771-doc dataset |

## Relevance filtering (in [[Assistant]])

- Semantic reranker score ≥ 1.0 (0-4 scale)
- Short specific-building queries: additionally filter by keyword match in building_name / file_name
- Cap at 3 results
- Returns JSON (not formatted text) so LLM formats in user's language

## keyword_search() — no embeddings

Used by dashboard Search tab. Full-text BM25 across all indexes. Returns raw list with `index` field.

## Connects to

[[Azure AI Search]] — the database
[[Indexer]] — writes to it
[[Assistant]] — reads via search_properties tool
[[API Prop Chat]] — exposes keyword_search via /api/search
