"""RAG Chatbot for Property Intelligence with LangGraph Memory.

Features:
- Bilingual (Traditional Chinese / English)
- Property recommendations
- Market analysis
- Source citations
- Conversation memory via LangGraph Checkpointing
"""

import os
import json
import uuid
from typing import Optional, Annotated, TypedDict
from dataclasses import dataclass, field
from operator import add

import httpx
from langsmith import traceable, trace
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from src.nodes.indexer import get_http_client, get_embedding, SEARCH_INDEXES


# ============ Data Classes ============

@dataclass
class ChatMessage:
    """A chat message."""
    role: str  # "user" or "assistant"
    content: str


@dataclass
class ChatResponse:
    """Response from the chatbot."""
    answer: str
    sources: list[dict] = field(default_factory=list)
    error: Optional[str] = None


# ============ LangGraph State ============

class ChatState(TypedDict):
    """State for the chatbot graph."""
    messages: Annotated[list[dict], add]  # Conversation history
    current_question: str
    context: str
    sources: list[dict]
    answer: str
    search_route: str  # "vector", "web", or "hybrid"


# ============ System Prompt ============

SYSTEM_PROMPT = """You are a Property Intelligence Assistant for Century 21 Hong Kong (世紀21香港).

## CRITICAL: Scope Restriction
You are STRICTLY a commercial property assistant. You can ONLY help with:
- Property listings (offices, retail shops, industrial units)
- Leasing information (rent, terms, availability)
- Property recommendations based on criteria
- Market analysis for Hong Kong commercial property
- Contact information for property agents

## OFF-TOPIC Handling
If the user asks about ANYTHING unrelated to Hong Kong commercial property, you MUST:
1. Politely decline to answer
2. Redirect them to property-related questions

Example responses for off-topic questions:
- English: "I'm a property assistant specializing in Hong Kong commercial real estate. I can help you find offices, retail spaces, or analyze market trends. How can I assist you with property matters today?"
- Chinese: "我是專門處理香港商業地產的物業助理。我可以幫您搜尋寫字樓、商舖，或分析市場趨勢。請問有什麼物業相關的問題我可以幫到您？"

DO NOT answer questions about: cooking, recipes, general knowledge, coding, travel, health, entertainment, sports, politics, or ANY topic outside commercial property.

## Conversation Memory
You have memory of previous messages in this conversation. Use this context to:
- Answer follow-up questions naturally
- Remember user preferences mentioned earlier
- Reference properties discussed before
- Maintain conversation continuity

## Your Capabilities (Property Only)
1. **Property Search**: Find properties matching criteria (location, size, rent, type)
2. **Recommendations**: Suggest suitable properties with reasoning
3. **Market Analysis**: Compare rents, identify trends from available data
4. **Information Extraction**: Answer questions about specific properties, terms, conditions

## Information Sources
You have access to TWO types of information:
1. **Internal Documents**: Property listings, contacts from our database (most reliable for specific properties)
2. **Web Search Results**: Latest news and market information from the internet (good for trends, news)

## Response Rules
1. **Language**: ALWAYS respond in the SAME language as the user's question
   - 繁體中文 question → 繁體中文 answer
   - English question → English answer

2. **Accuracy**: Use information from BOTH internal documents and web results
   - Prioritize internal documents for specific property details
   - Use web results for market trends, news, and general information
   - If not found: "根據現有資料，我未能找到相關資訊。" or "I couldn't find this in the available documents."
   - NEVER make up information

3. **Citations**: Always cite sources
   - Internal documents: (來源: filename) or (Source: filename)
   - Web results: (來源: article title) or (Source: article title)

4. **Recommendations**: List 2-3 best matches with:
   - Location, size, rent, property type
   - WHY each is suitable

5. **Market Analysis**:
   - Compare similar properties
   - Note rent ranges
   - Be clear about data limitations

## Response Format
- Bullet points for lists
- NEVER use markdown tables (| col | col |) — they do not render in WhatsApp or the dashboard chat
- For comparisons, use bullet points or numbered lists instead
- Structure: Summary → Details → Sources

## Available Property Information
{context}

---
Based ONLY on the above property information, help the user. Stay strictly within the commercial property domain."""


CHATBOT_PROJECT = "property-chatbot"  # Separate LangSmith project


# ============ Reranking ============

RERANK_PROMPT = """Score how relevant each document is to the query. Return ONLY a JSON array of scores (0-10).

Query: {query}

Documents:
{documents}

Return JSON array of scores, one per document (0=not relevant, 10=highly relevant):
Example: [8, 3, 9, 5, 2]

Scores:"""


@traceable(name="rerank_documents", run_type="chain", project_name=CHATBOT_PROJECT)
def rerank_documents(query: str, documents: list[dict], top_k: int = 5) -> list[dict]:
    """Rerank documents using LLM for better relevance.

    Uses OpenRouter (DeepSeek) to score document relevance - no extra API key needed.

    Args:
        query: Original search query
        documents: List of documents from initial search
        top_k: Number of top results to return after reranking

    Returns:
        Reranked list of documents (most relevant first)
    """
    if not documents:
        return []

    if len(documents) <= top_k:
        return documents  # No need to rerank if we have fewer than top_k

    try:
        # Prepare document summaries for reranking
        doc_summaries = []
        for i, doc in enumerate(documents):
            summary_parts = [f"[{i}] {doc.get('file_name', 'Unknown')}"]
            extracted = doc.get("extracted_data", {})
            if extracted:
                for key in ["building_name", "address", "district", "rent_monthly", "size_sqft"]:
                    if extracted.get(key):
                        summary_parts.append(f"{key}: {extracted[key]}")
            if doc.get("content"):
                summary_parts.append(doc["content"][:200])
            doc_summaries.append(" | ".join(summary_parts))

        documents_text = "\n".join(doc_summaries)

        from src.utils.llm import chat_complete
        rerank_messages = [{"role": "user", "content": RERANK_PROMPT.format(query=query, documents=documents_text)}]
        content = chat_complete(rerank_messages, max_tokens=100, temperature=0, fallback_model="deepseek/deepseek-chat")

        # Parse scores from response
        import re
        match = re.search(r'\[[\d,\s\.]+\]', content)
        if match:
            scores = json.loads(match.group())
            # Pair documents with scores and sort
            scored_docs = list(zip(documents, scores))
            scored_docs.sort(key=lambda x: float(x[1]), reverse=True)
            return [doc for doc, _ in scored_docs[:top_k]]

        return documents[:top_k]

    except Exception:
        # On error, return original order
        return documents[:top_k]


# ============ Multi-Query Generation ============

MULTI_QUERY_PROMPT = """You are an AI assistant helping to generate alternative search queries for a Hong Kong commercial property search system.

Given the original query, generate 3 alternative versions that:
1. Use different wording but same intent
2. Include both English AND Chinese variations if original is in one language
3. Focus on different aspects (location, size, price, property type)

Original query: {query}

Return ONLY a JSON array of 3 alternative queries, no explanation:
["query 1", "query 2", "query 3"]"""


@traceable(name="generate_query_variations", run_type="llm", project_name=CHATBOT_PROJECT)
def generate_query_variations(query: str) -> list[str]:
    """Generate alternative search queries using LLM.

    Args:
        query: Original user query

    Returns:
        List of query variations (including original)
    """
    try:
        from src.utils.llm import chat_complete
        variation_messages = [{"role": "user", "content": MULTI_QUERY_PROMPT.format(query=query)}]
        content = chat_complete(variation_messages, max_tokens=200, temperature=0.7, fallback_model="deepseek/deepseek-chat")

        # Parse JSON array
        import re
        # Find JSON array in response
        match = re.search(r'\[.*?\]', content, re.DOTALL)
        if match:
            variations = json.loads(match.group())
            # Return original + variations (deduplicated)
            all_queries = [query] + [v for v in variations if v != query]
            return all_queries[:4]  # Max 4 queries total

        return [query]

    except Exception:
        return [query]  # Fallback to original on any error


# ============ Node Functions ============

def _search_single_index(
    query: str,
    query_embedding: list[float],
    index_name: str,
    top_k: int = 5
) -> list[dict]:
    """Search a single index. Internal helper function.

    Handles different index schemas gracefully:
    - processed-documents: file_name, extracted_data, processed_at, image_urls
    - c21net-intelligence-v2: title, last_updated (no extracted_data/image_urls)
    """
    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    api_key = os.environ.get("AZURE_SEARCH_API_KEY")

    search_url = f"{endpoint}/indexes/{index_name}/docs/search?api-version=2024-07-01"
    headers = {
        "Content-Type": "application/json",
        "api-key": api_key,
    }

    client = get_http_client()

    index_configs = {
        "property-intel-index": {
            "select": "id,file_name,document_type,content,extracted_data,building_name,processed_at,image_urls,source_url",
            "searchFields": "content,file_name",
            "semanticConfig": "default-semantic-config",
        },
    }

    # Get config for this index (fallback to minimal fields)
    config = index_configs.get(index_name, {
        "select": "id,document_type,content",
        "searchFields": "content",
        "semanticConfig": None,
    })

    # Try full hybrid + semantic search first
    body_full = {
        "vectorQueries": [
            {
                "kind": "vector",
                "vector": query_embedding,
                "fields": "content_vector",
                "k": top_k,
            }
        ],
        "search": query,
        "searchFields": config["searchFields"],
        "select": config["select"],
        "top": top_k,
    }

    # Only add semantic config if index has one
    if config.get("semanticConfig"):
        body_full["queryType"] = "semantic"
        body_full["semanticConfiguration"] = config["semanticConfig"]
        body_full["captions"] = "extractive"

    try:
        response = client.post(search_url, headers=headers, json=body_full)
        response.raise_for_status()
        results = response.json().get("value", [])
        print(f"[search_documents] Index {index_name}: {len(results)} results (hybrid+semantic)")
        return results
    except Exception as e:
        print(f"[search_documents] Index {index_name}: hybrid+semantic failed ({e}), trying keyword only")

    # Fallback to keyword-only search (no vector, no semantic)
    body_simple = {
        "search": query,
        "searchFields": config["searchFields"],
        "select": config["select"],
        "top": top_k,
    }

    try:
        response = client.post(search_url, headers=headers, json=body_simple)
        response.raise_for_status()
        results = response.json().get("value", [])
        print(f"[search_documents] Index {index_name}: {len(results)} results (keyword only)")
        return results
    except Exception as e:
        print(f"[search_documents] Index {index_name}: all search methods failed - {e}")
        return []


@traceable(name="search_documents", run_type="retriever", project_name=CHATBOT_PROJECT)
def search_documents(query: str, top_k: int = 5, hybrid: bool = True) -> list[dict]:
    """Search vector database for relevant documents using hybrid search.

    Searches all indexes configured in AZURE_SEARCH_INDEXES (comma-separated).
    Defaults to AZURE_SEARCH_INDEX if not set.

    Args:
        query: Search query text
        top_k: Number of results to return
        hybrid: If True, use vector + keyword search. If False, vector only.
    """
    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    api_key = os.environ.get("AZURE_SEARCH_API_KEY")

    if not all([endpoint, api_key]):
        return []

    # Get embedding for query (once, reused for all indexes)
    query_embedding = get_embedding(query)

    # Search all configured indexes
    all_results = []
    for index_name in SEARCH_INDEXES:
        results = _search_single_index(query, query_embedding, index_name, top_k)
        for doc in results:
            doc["_index"] = index_name  # Track source index
        all_results.extend(results)

    # Format and deduplicate results
    documents = []
    seen_files = set()   # dedup by file_name
    seen_buildings = set()  # dedup by building_name/project_name across indexes

    for doc in all_results:
        # Normalize file_name: c21net-intelligence-v2 uses "title" instead
        file_name = doc.get("file_name") or doc.get("title") or "Unknown"

        # Deduplicate by file_name
        if file_name in seen_files:
            continue
        seen_files.add(file_name)

        extracted = doc.get("extracted_data", "{}")
        if isinstance(extracted, str):
            try:
                extracted = json.loads(extracted)
            except:
                extracted = {}

        # Secondary dedup by building/project name (catches same building across indexes)
        building_key = (
            extracted.get("building_name") or extracted.get("project_name")
            or doc.get("x_name") or ""
        ).strip().lower()
        if building_key and building_key in seen_buildings:
            continue
        if building_key:
            seen_buildings.add(building_key)

        # Get semantic caption if available
        captions = doc.get("@search.captions", [])
        caption_text = captions[0].get("text", "") if captions else ""

        documents.append({
            "file_name": file_name,
            "document_type": doc.get("document_type", "unknown"),
            "content": doc.get("content", "")[:2000],
            "extracted_data": extracted,
            "image_urls": doc.get("image_urls", []),
            "source_url": doc.get("source_url", ""),
            "score": doc.get("@search.score", 0),
            "reranker_score": doc.get("@search.rerankerScore", 0),
            "caption": caption_text,
            "index": doc.get("_index", ""),  # Source index for debugging
        })

    # Sort by reranker score if available (semantic ranking)
    documents.sort(key=lambda x: x.get("reranker_score", 0), reverse=True)

    # Log summary
    index_counts = {}
    for d in documents:
        idx = d.get("index", "unknown")
        index_counts[idx] = index_counts.get(idx, 0) + 1
    print(f"[search_documents] Total: {len(documents)} results from {index_counts}")

    # Limit to top_k after merging
    return documents[:top_k]


@traceable(name="multi_query_search", run_type="retriever", project_name=CHATBOT_PROJECT)
def multi_query_search(query: str, top_k: int = 5, use_rerank: bool = True) -> list[dict]:
    """Search using multiple query variations for better recall, with optional reranking.

    Pipeline:
    1. Generate 3-4 query variations (including bilingual)
    2. Search with each variation IN PARALLEL
    3. Combine and deduplicate results
    4. Rerank using LLM (if enabled)
    5. Return top results

    Args:
        query: Original search query
        top_k: Final number of results to return
        use_rerank: Whether to apply reranking (default True)

    Returns:
        List of unique documents, reranked for relevance
    """
    from concurrent.futures import ThreadPoolExecutor

    # Generate query variations
    queries = generate_query_variations(query)

    # Search with each query IN PARALLEL - fetch more for reranking
    fetch_k = 15 if use_rerank else top_k
    seen_files = {}  # file_name -> (doc, count)

    # Run all searches in parallel
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_query = {
            executor.submit(search_documents, q, fetch_k, True): q
            for q in queries
        }

        for future in future_to_query:
            try:
                results = future.result(timeout=15)
                for doc in results:
                    fname = doc["file_name"]
                    if fname in seen_files:
                        seen_files[fname] = (doc, seen_files[fname][1] + 1)
                    else:
                        seen_files[fname] = (doc, 1)
            except Exception:
                pass  # Continue with other results

    # Sort by frequency (found by more queries = more relevant)
    sorted_results = sorted(
        seen_files.values(),
        key=lambda x: (x[1], x[0].get("score", 0)),  # frequency, then score
        reverse=True
    )

    candidates = [doc for doc, _ in sorted_results]

    # Apply reranking if enabled
    if use_rerank and candidates:
        return rerank_documents(query, candidates, top_k=top_k)

    return candidates[:top_k]


def _keyword_search_single_index(
    query: str,
    index_name: str,
    filters: dict = None,
    top_k: int = 20,
) -> list[dict]:
    """Search a single index with keyword search. Internal helper.

    Handles different index schemas gracefully.
    """
    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    api_key = os.environ.get("AZURE_SEARCH_API_KEY")

    search_url = f"{endpoint}/indexes/{index_name}/docs/search?api-version=2024-07-01"
    headers = {
        "Content-Type": "application/json",
        "api-key": api_key,
    }

    has_query = bool(query and query.strip())

    index_configs = {
        "property-intel-index": {
            "select": "id,file_name,document_type,content,extracted_data,building_name,processed_at,image_urls,source_url",
            "searchFields": "content,file_name",
            "semanticConfig": "default-semantic-config",
            "orderBy": "processed_at desc",
        },
    }

    config = index_configs.get(index_name, {
        "select": "id,document_type,content",
        "searchFields": "content",
        "semanticConfig": None,
        "orderBy": None,
    })

    body = {
        "search": query if has_query else "*",
        "searchFields": config["searchFields"],
        "select": config["select"],
        "top": top_k,
    }

    if not has_query and config.get("orderBy"):
        body["orderby"] = config["orderBy"]

    filter_parts = []
    if filters:
        if filters.get("document_type"):
            filter_parts.append(f"document_type eq '{filters['document_type']}'")

    if filter_parts:
        body["filter"] = " and ".join(filter_parts)

    client = get_http_client()

    # Try with semantic ranking first (if index supports it)
    if has_query and config.get("semanticConfig"):
        body_semantic = body.copy()
        body_semantic["queryType"] = "semantic"
        body_semantic["semanticConfiguration"] = config["semanticConfig"]
        body_semantic["captions"] = "extractive"
        try:
            response = client.post(search_url, headers=headers, json=body_semantic)
            response.raise_for_status()
            print(f"[keyword_search] Index {index_name}: {len(response.json().get('value', []))} results (semantic)")
            return response.json().get("value", [])
        except Exception as e:
            # Semantic search failed, fall back to simple search
            print(f"[keyword_search] Index {index_name}: semantic search failed ({e}), trying simple search")

    # Simple search (no semantic ranking)
    try:
        response = client.post(search_url, headers=headers, json=body)
        response.raise_for_status()
        print(f"[keyword_search] Index {index_name}: {len(response.json().get('value', []))} results (simple)")
        return response.json().get("value", [])
    except Exception as e:
        print(f"[keyword_search] Index {index_name}: search failed - {e}")
        return []


def keyword_search(
    query: str = "",
    filters: dict = None,
    top_k: int = 20,
) -> list[dict]:
    """Direct keyword search without LLM - for Search tab.

    Searches all indexes configured in AZURE_SEARCH_INDEXES (comma-separated).

    Args:
        query: Search keywords (optional)
        filters: Dict with optional keys: document_type, district
        top_k: Number of results

    Returns:
        List of matching documents with extracted data (includes 'index' field)
    """
    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    api_key = os.environ.get("AZURE_SEARCH_API_KEY")

    if not all([endpoint, api_key]):
        return []

    # Search all configured indexes
    all_results = []
    for index_name in SEARCH_INDEXES:
        index_results = _keyword_search_single_index(query, index_name, filters, top_k)
        for doc in index_results:
            doc["_index"] = index_name  # Track source index
        all_results.extend(index_results)

    # Combine results - use all_results instead of single index results
    results = all_results
    has_query = bool(query and query.strip())

    # Filter out low-relevance results when searching (not browsing)
    # Semantic reranker score ~2.5+ indicates good relevance
    MIN_RERANKER_SCORE = 2.5
    IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')

    if has_query:
        results = [
            r for r in results
            if r.get("@search.rerankerScore", 0) >= MIN_RERANKER_SCORE
            and not (r.get("file_name") or r.get("title") or "").lower().endswith(IMAGE_EXTENSIONS)
        ]

    # Client-side district filtering (since district is in extracted_data JSON)
    # Map English district names to Chinese equivalents for matching
    DISTRICT_ALIASES = {
        "central": ["中環", "central"],
        "中環": ["中環", "central"],
        "admiralty": ["金鐘", "admiralty"],
        "金鐘": ["金鐘", "admiralty"],
        "wan chai": ["灣仔", "wan chai", "wanchai"],
        "灣仔": ["灣仔", "wan chai", "wanchai"],
        "causeway bay": ["銅鑼灣", "causeway bay"],
        "銅鑼灣": ["銅鑼灣", "causeway bay"],
        "north point": ["北角", "north point"],
        "北角": ["北角", "north point"],
        "quarry bay": ["鰂魚涌", "quarry bay"],
        "鰂魚涌": ["鰂魚涌", "quarry bay"],
        "tsim sha tsui": ["尖沙咀", "tsim sha tsui", "tst"],
        "尖沙咀": ["尖沙咀", "tsim sha tsui", "tst"],
        "mong kok": ["旺角", "mong kok"],
        "旺角": ["旺角", "mong kok"],
        "kowloon bay": ["九龍灣", "kowloon bay"],
        "九龍灣": ["九龍灣", "kowloon bay"],
        "kwun tong": ["觀塘", "kwun tong"],
        "觀塘": ["觀塘", "kwun tong"],
        "cheung sha wan": ["長沙灣", "cheung sha wan"],
        "長沙灣": ["長沙灣", "cheung sha wan"],
        "lai chi kok": ["荔枝角", "lai chi kok"],
        "荔枝角": ["荔枝角", "lai chi kok"],
        "tsuen wan": ["荃灣", "tsuen wan"],
        "荃灣": ["荃灣", "tsuen wan"],
        "kwai chung": ["葵涌", "kwai chung"],
        "葵涌": ["葵涌", "kwai chung"],
    }

    district_filter = filters.get("district") if filters else None
    if district_filter:
        # Get all aliases for the filter
        filter_lower = district_filter.lower()
        aliases = DISTRICT_ALIASES.get(filter_lower, [filter_lower])

        filtered_results = []
        for doc in results:
            extracted = doc.get("extracted_data", "{}")
            if isinstance(extracted, str):
                try:
                    extracted = json.loads(extracted)
                except:
                    extracted = {}
            doc_district = (extracted.get("district") or "").lower()
            # Match if any alias is in the district
            if any(alias.lower() in doc_district for alias in aliases):
                filtered_results.append(doc)
        results = filtered_results

    # Format and deduplicate results (by file_name, keep first/highest score)
    documents = []
    seen_files = set()

    # Sort by reranker score (descending) if available, then by search score
    results.sort(key=lambda x: (x.get("@search.rerankerScore", 0), x.get("@search.score", 0)), reverse=True)

    for doc in results:
        # Normalize file_name: c21net-intelligence-v2 uses "title" instead
        file_name = doc.get("file_name") or doc.get("title") or "Unknown"

        # Deduplicate by file_name
        if file_name in seen_files:
            continue
        seen_files.add(file_name)

        extracted = doc.get("extracted_data", "{}")
        if isinstance(extracted, str):
            try:
                extracted = json.loads(extracted)
            except:
                extracted = {}

        documents.append({
            "id": doc.get("id", ""),
            "file_name": file_name,
            "document_type": doc.get("document_type", "unknown"),
            "content": doc.get("content", "")[:500],
            "extracted_data": extracted,
            "image_urls": doc.get("image_urls", []),
            "processed_at": doc.get("processed_at") or "",
            "score": doc.get("@search.score", 0),
            "index": doc.get("_index", ""),  # Source index
        })

    return documents


@traceable(name="web_search", run_type="retriever", project_name=CHATBOT_PROJECT)
def web_search(query: str, max_results: int = 3) -> list[dict]:
    """Search the web for relevant information using Tavily.

    Args:
        query: Search query
        max_results: Maximum number of results

    Returns:
        List of web search results
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        # Return error info so it's visible in LangSmith
        return [{"error": "TAVILY_API_KEY not set", "source": "web"}]

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)

        # Add Hong Kong property context to improve relevance
        search_query = f"Hong Kong commercial property real estate {query}"

        response = client.search(
            query=search_query,
            search_depth="basic",
            max_results=max_results,
        )

        results = []
        for r in response.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", "")[:500],
                "source": "web",
            })

        # If no results, return info message
        if not results:
            return [{"error": "No web results found", "query": search_query, "source": "web"}]

        return results

    except Exception as e:
        # Return error info so it's visible in LangSmith
        return [{"error": f"Web search failed: {str(e)}", "source": "web"}]


def build_context(documents: list[dict], web_results: list[dict] = None) -> str:
    """Build context string from retrieved documents and web results."""
    if not documents and not web_results:
        return "No relevant documents found."

    context_parts = []

    for i, doc in enumerate(documents, 1):
        doc_type = doc.get("document_type", "unknown")
        file_name = doc.get("file_name", "Unknown")
        extracted = doc.get("extracted_data", {})
        content = doc.get("content", "")
        source_url = doc.get("source_url", "")

        if doc_type == "listing":
            context_parts.append(f"""
---
**Document {i}: {file_name}** (Type: Single Listing)
- Building: {extracted.get('building_name', 'N/A')}
- Address: {extracted.get('address', 'N/A')}
- District: {extracted.get('district', 'N/A')}
- Property Type: {extracted.get('property_type', 'N/A')}
- Size: {extracted.get('size_sqft', 'N/A')} sqft
- Rent: HK${extracted.get('rent_monthly', 'N/A')}/month
- Floor/Unit: {extracted.get('floor', 'N/A')} {extracted.get('unit', '')}
- Contact: {extracted.get('contact_name', 'N/A')} {extracted.get('contact_phone', '')}
{f'- Source Document: {source_url}' if source_url else ''}
Content Preview:
{content[:500]}
""")
        elif doc_type == "listing_list":
            units = extracted.get('units', [])
            units_str = ""
            for u in units[:5]:
                units_str += f"  - {u.get('floor', 'N/A')} {u.get('unit', '')}: {u.get('size', 'N/A')} sqft, HK${u.get('rent', 'N/A')}/month\n"

            context_parts.append(f"""
---
**Document {i}: {file_name}** (Type: Multi Listing)
- Building: {extracted.get('building_name', 'N/A')}
- Address: {extracted.get('address', 'N/A')}
- District: {extracted.get('district', 'N/A')}
- Contact: {extracted.get('contact_phone', 'N/A')}
- Available Units:
{units_str}{f'- Source Document: {source_url}' if source_url else ''}
Content Preview:
{content[:300]}
""")
        elif doc_type == "pitching_deck":
            # Rich project/development information
            summary = extracted.get('project_summary', {})
            location = extracted.get('location', {})
            available_units = extracted.get('available_units', [])
            units_str = ""
            for u in available_units[:5]:
                units_str += f"  - {u.get('unit', '')} ({u.get('floor', '')}): {u.get('size_sqft', 'N/A')} sqft, {u.get('facing', '')}\n"

            context_parts.append(f"""
---
**Document {i}: {file_name}** (Type: Pitching Deck)
- Project: {extracted.get('project_name', 'N/A')} {extracted.get('project_name_zh', '')}
- Developer: {extracted.get('developer', 'N/A')}
- Address: {extracted.get('address', 'N/A')}
- District: {extracted.get('district', 'N/A')}
- Property Type: {extracted.get('property_type', 'N/A')}
- Project Summary:
  - Retail: {summary.get('retail_area_sqft', 'N/A')} sqft ({summary.get('floors_retail', 'N/A')} floors)
  - Office: {summary.get('office_area_sqft', 'N/A')} sqft ({summary.get('floors_office', 'N/A')} floors)
  - Residential: {summary.get('residential_units', 'N/A')} units
  - Theatre: {summary.get('theatre_seats', 'N/A')} seats
- Availability: {extracted.get('availability_date', 'N/A')}
- Location:
  - MTR: {', '.join(location.get('mtr_stations', [])) if location.get('mtr_stations') else 'N/A'}
  - Catchment Population: {location.get('catchment_population', 'N/A')}
  - Nearby Office Area: {location.get('nearby_office_sqft', 'N/A')} sqft
  - Nearby Hotels: {location.get('nearby_hotels_rooms', 'N/A')} rooms
- Key Features: {', '.join(extracted.get('key_features', [])[:5]) if extracted.get('key_features') else 'N/A'}
- Available Units for Lease:
{units_str if units_str else '  - Contact for details'}
{f'- Source Document: {source_url}' if source_url else ''}
Content Preview:
{content[:300]}
""")
        elif doc_type == "news":
            context_parts.append(f"""
---
**Document {i}: {file_name}** (Type: News Article)
- Title: {extracted.get('title', 'N/A')} {extracted.get('title_zh', '')}
- Date: {extracted.get('date', 'N/A')}
- Source: {extracted.get('source', 'N/A')}
- Summary: {extracted.get('summary', 'N/A')}
- Topics: {', '.join(extracted.get('topics', [])) if extracted.get('topics') else 'N/A'}

Content Preview:
{content[:500]}
""")
        else:
            context_parts.append(f"""
---
**Document {i}: {file_name}** (Type: {doc_type})
{json.dumps(extracted, ensure_ascii=False, indent=2) if extracted else ''}

Content Preview:
{content[:500]}
""")

    # Add web results if available (skip error objects)
    if web_results:
        valid_results = [r for r in web_results if "error" not in r]
        if valid_results:
            context_parts.append("\n---\n## Web Search Results (Latest Information)\n")
            for i, r in enumerate(valid_results, 1):
                context_parts.append(f"""
**Web Result {i}: {r.get('title', 'N/A')}**
Source: {r.get('url', 'N/A')}
{r.get('content', '')}
""")

    return "\n".join(context_parts)


@traceable(name="route_query", run_type="chain", project_name=CHATBOT_PROJECT)
def route_query(query: str) -> str:
    """Determine which search method to use based on query content.

    Returns:
        "vector" - search internal documents only
        "web" - search web only
        "hybrid" - search both
        "report" - generate a report
    """
    query_lower = query.lower()

    # Check for report intent first
    report_keywords = [
        "報告", "報表", "生成", "製作", "整理報告",
        "report", "generate report", "create report",
    ]
    report_type_keywords = [
        "租金分析", "空置", "市場概覽", "聯絡人",
        "rent analysis", "availability", "market overview",
    ]

    has_report_keyword = any(kw in query_lower for kw in report_keywords)
    has_report_type = any(kw in query_lower for kw in report_type_keywords)

    if has_report_keyword or has_report_type:
        return "report"

    # Strong web indicators - if ANY of these, go web-only
    web_only_patterns = [
        "市場趨勢", "市場走勢", "樓市", "房地產市場", "地產市場",
        "market trend", "market outlook", "property market",
        "分析報告", "市場分析", "行情", "前景", "展望",
    ]

    # If query is clearly about market trends, go web only
    if any(pattern in query_lower for pattern in web_only_patterns):
        return "web"

    # Keywords indicating web search (news, trends, market analysis)
    web_keywords = [
        "趨勢", "走勢", "市場", "新聞", "最新", "預測",
        "trend", "news", "market", "forecast", "outlook", "analysis",
        "2024", "2025", "2026",  # Recent year queries
        "今年", "去年", "最近", "未來",
    ]

    # Keywords indicating vector search (specific property queries)
    vector_keywords = [
        "有什麼", "有咩", "邊度有", "搵", "找", "出租", "招租",
        "寫字樓", "商舖", "工廈", "倉庫", "office", "retail", "industrial",
        "呎租", "租金", "面積", "聯絡", "contact",
        # District names - Hong Kong Island
        "中環", "金鐘", "灣仔", "銅鑼灣", "北角", "鰂魚涌", "太古", "西灣河", "筲箕灣", "柴灣",
        "上環", "西營盤", "堅尼地城", "香港仔", "黃竹坑",
        # District names - Kowloon
        "尖沙咀", "佐敦", "油麻地", "旺角", "太子", "深水埗", "長沙灣", "荔枝角",
        "九龍灣", "觀塘", "牛頭角", "藍田", "油塘", "將軍澳",
        "九龍城", "土瓜灣", "紅磡", "黃大仙", "鑽石山", "新蒲崗",
        # District names - New Territories
        "葵涌", "葵芳", "荃灣", "青衣", "沙田", "火炭", "大圍", "馬鞍山",
        "大埔", "粉嶺", "上水", "元朗", "天水圍", "屯門",
        # Building name keywords
        "廣場", "中心", "大廈", "商場", "工業", "企業",
        # English district names
        "central", "admiralty", "wan chai", "causeway bay", "north point",
        "tsim sha tsui", "jordan", "mongkok", "kowloon bay", "kwun tong",
        "sha tin", "tsuen wan", "kwai chung", "tuen mun", "yuen long",
    ]

    # Keywords indicating hybrid (comparison, both needed)
    hybrid_keywords = [
        "比較", "對比", "compare", "versus", "vs",
        "同埋", "以及", "and also",
    ]

    # Check for hybrid first (comparison queries)
    if any(kw in query_lower for kw in hybrid_keywords):
        return "hybrid"

    # Count matches for web vs vector
    web_score = sum(1 for kw in web_keywords if kw in query_lower)
    vector_score = sum(1 for kw in vector_keywords if kw in query_lower)

    # Decide based on scores - default to hybrid for property search system
    if web_score > 0 and vector_score == 0:
        return "web"
    elif vector_score > 0 and web_score == 0:
        return "vector"
    elif web_score > vector_score:
        return "web"
    elif vector_score > web_score:
        return "vector"
    else:
        return "hybrid"  # Default to hybrid when tied or no matches (property system)


def retrieve_node(state: ChatState) -> dict:
    """Node: Search for relevant documents and/or web based on query type.

    Uses fast single-query search for quick responses.
    Azure AI Search semantic ranking provides good relevance.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    question = state["current_question"]

    # Route query to determine search strategy
    route = route_query(question)

    # Handle report requests separately
    if route == "report":
        return _handle_report_request(question)

    documents = []
    web_results = []

    # Run searches in PARALLEL for better latency
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {}

        if route in ("vector", "hybrid"):
            # Use direct search (fast) instead of multi_query_search (slow)
            # Fetch 10 results to include documents from multiple indexes
            futures["docs"] = executor.submit(search_documents, question, 10, True)

        if route in ("web", "hybrid"):
            futures["web"] = executor.submit(web_search, question, 3)

        # Collect results as they complete
        for key, future in futures.items():
            try:
                if key == "docs":
                    documents = future.result(timeout=30)
                elif key == "web":
                    web_results = future.result(timeout=15)
            except Exception:
                pass  # Continue with partial results

    # Build combined context
    context = build_context(documents, web_results)

    # Build sources list - include all fields needed for report generation
    sources = []
    for doc in documents:
        sources.append({
            "file_name": doc["file_name"],
            "document_type": doc["document_type"],
            "image_urls": doc.get("image_urls", []),
            "score": doc.get("score", 0),
            "index": doc.get("index", ""),
            "source_url": doc.get("source_url", ""),
            "type": "document",
            # Fields for report generation
            "extracted_data": doc.get("extracted_data", {}),
            "content": doc.get("content", ""),
            # c21net-specific fields (at root level)
            "monthly_rental_hkd": doc.get("monthly_rental_hkd"),
            "floor_area_sqft": doc.get("floor_area_sqft"),
            "title": doc.get("title"),  # c21net uses title instead of file_name
        })
    # Only add valid web results (not errors)
    for r in web_results:
        if "error" not in r:
            sources.append({
                "file_name": r.get("title", "Web Result"),
                "url": r.get("url", ""),
                "type": "web",
            })

    return {"context": context, "sources": sources, "search_route": route}


def _handle_report_request(question: str) -> dict:
    """Handle report generation requests.

    Returns state update with report context or prompt for more info.
    """
    try:
        from src.nodes.report_generator.main import handle_report_request

        response = handle_report_request(question)

        if not response.is_report_request:
            # Not actually a report request, fall back to normal search
            return {
                "context": "",
                "sources": [],
                "search_route": "hybrid"
            }

        if response.needs_more_info:
            # Need more info from user - return prompt as context
            return {
                "context": f"[REPORT_PROMPT]\n{response.prompt_message}",
                "sources": [],
                "search_route": "report"
            }

        if response.error:
            return {
                "context": f"[REPORT_ERROR]\n{response.error}",
                "sources": [],
                "search_route": "report"
            }

        if response.report:
            # Report generated successfully
            report = response.report
            context = f"[REPORT_GENERATED]\n"
            context += f"title: {report.title}\n"
            context += f"title_en: {report.title_en}\n"
            context += f"summary: {report.summary_markdown}\n"
            context += f"document_count: {report.document_count}\n"
            if report.pdf_url:
                context += f"pdf_url: {report.pdf_url}\n"
            if report.error:
                context += f"note: {report.error}\n"

            sources = [{
                "file_name": report.filename or f"{report.title}.pdf",
                "document_type": "report",
                "type": "report",
                "pdf_url": report.pdf_url,
                "pdf_bytes": report.pdf_bytes,  # For direct download
            }]

            return {
                "context": context,
                "sources": sources,
                "search_route": "report"
            }

    except ImportError as e:
        return {
            "context": f"[REPORT_ERROR]\nReport generator not available: {e}",
            "sources": [],
            "search_route": "report"
        }
    except Exception as e:
        return {
            "context": f"[REPORT_ERROR]\nReport generation failed: {e}",
            "sources": [],
            "search_route": "report"
        }

    return {
        "context": "",
        "sources": [],
        "search_route": "hybrid"
    }


def _build_llm_messages(question: str, context: str, messages: list[dict]) -> list[dict]:
    """Build messages array for LLM."""
    llm_messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(context=context)}
    ]
    # Add conversation history (last 10 messages)
    for msg in messages[-10:]:
        llm_messages.append({"role": msg["role"], "content": msg["content"]})
    # Add current question
    llm_messages.append({"role": "user", "content": question})
    return llm_messages


@traceable(name="generate_answer", run_type="llm", project_name=CHATBOT_PROJECT)
def call_llm(question: str, context: str, messages: list[dict]) -> str:
    """Call LLM to generate answer (non-streaming). Prefers Azure OpenAI."""
    from src.utils.llm import azure_openai_available, chat_complete
    llm_messages = _build_llm_messages(question, context, messages)
    try:
        if azure_openai_available():
            return chat_complete(llm_messages, max_tokens=2000, temperature=0.5)
        # Fallback: OpenRouter
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("No LLM configured")
        url = "https://openrouter.ai/api/v1/chat/completions"
        body = {"model": "meta-llama/llama-3.3-70b-instruct", "messages": llm_messages, "temperature": 0.5, "max_tokens": 2000}
        client = get_http_client()
        response = client.post(url, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json=body, timeout=30)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except httpx.TimeoutException:
        return "Sorry, the response took too long. Please try again. 抱歉，回應超時，請重試。"
    except Exception as e:
        return f"Error generating response: {str(e)}"


def call_llm_stream(question: str, context: str, messages: list[dict]):
    """Call LLM with streaming - yields text chunks. Prefers Azure OpenAI.

    Note: Not using @traceable decorator here because it doesn't handle
    GeneratorExit well - logs it as error when user navigates away.
    """
    from src.utils.llm import azure_openai_available, chat_complete_stream
    llm_messages = _build_llm_messages(question, context, messages)
    try:
        if azure_openai_available():
            yield from chat_complete_stream(llm_messages, max_tokens=2000, temperature=0.5)
            return
        # Fallback: OpenRouter
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("No LLM configured")
        url = "https://openrouter.ai/api/v1/chat/completions"
        body = {"model": "meta-llama/llama-3.3-70b-instruct", "messages": llm_messages, "temperature": 0.5, "max_tokens": 2000, "stream": True}
        with httpx.Client(timeout=60) as client:
            with client.stream("POST", url, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json=body) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        raw = line[6:]
                        if raw == "[DONE]":
                            break
                        try:
                            chunk = json.loads(raw)
                            content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
    except GeneratorExit:
        return


def generate_node(state: ChatState) -> dict:
    """Node: Generate answer using LLM."""
    context = state["context"]
    question = state["current_question"]

    # Handle report responses directly (no LLM needed)
    if context.startswith("[REPORT_PROMPT]"):
        # Return the prompt for more info
        answer = context.replace("[REPORT_PROMPT]\n", "")
        new_messages = [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer}
        ]
        return {"answer": answer, "messages": new_messages}

    if context.startswith("[REPORT_GENERATED]"):
        # Extract summary from context
        lines = context.split("\n")
        summary = ""
        for line in lines:
            if line.startswith("summary: "):
                summary = line.replace("summary: ", "")
                break

        answer = summary if summary else "報告已生成 Report generated"
        new_messages = [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer}
        ]
        return {"answer": answer, "messages": new_messages}

    if context.startswith("[REPORT_ERROR]"):
        answer = context.replace("[REPORT_ERROR]\n", "")
        new_messages = [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer}
        ]
        return {"answer": answer, "messages": new_messages}

    # Normal LLM generation
    answer = call_llm(
        question,
        context,
        state.get("messages", [])
    )
    # Add the exchange to messages for memory
    new_messages = [
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer}
    ]
    return {"answer": answer, "messages": new_messages}


# ============ Graph Builder ============

def create_chatbot_graph() -> StateGraph:
    """Create the chatbot graph."""
    graph = StateGraph(ChatState)

    # Add nodes
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)

    # Add edges
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)

    return graph


# ============ Memory & Compiled Graph ============

# In-memory checkpointer for conversation persistence
memory = MemorySaver()

# Compile graph with memory (for dashboard use)
chatbot_graph = create_chatbot_graph().compile(checkpointer=memory)

# Compile graph without checkpointer (for LangGraph Studio - it provides its own)
chatbot_graph_studio = create_chatbot_graph().compile()


# ============ Public API ============

@traceable(name="chat", run_type="chain", project_name=CHATBOT_PROJECT)
def chat(
    question: str,
    thread_id: str = None,
    chat_history: list[ChatMessage] = None,  # Kept for backward compatibility
) -> ChatResponse:
    """Main chat function with memory.

    Args:
        question: User's question
        thread_id: Conversation thread ID (for memory persistence)
        chat_history: Previous conversation (deprecated, use thread_id)

    Returns:
        ChatResponse with answer and sources
    """
    # Generate thread_id if not provided
    if not thread_id:
        thread_id = str(uuid.uuid4())

    try:
        # Run the graph with thread config for memory
        config = {"configurable": {"thread_id": thread_id}}

        result = chatbot_graph.invoke(
            {
                "current_question": question,
                "context": "",
                "sources": [],
                "answer": "",
                "messages": [],
            },
            config=config
        )

        return ChatResponse(
            answer=result["answer"],
            sources=result["sources"]
        )

    except httpx.HTTPStatusError as e:
        return ChatResponse(
            answer="",
            error=f"API error: {e.response.status_code}"
        )
    except Exception as e:
        return ChatResponse(
            answer="",
            error=f"Error: {str(e)}"
        )


@dataclass
class StreamingChatResponse:
    """Response container for streaming chat."""
    sources: list[dict] = field(default_factory=list)
    error: Optional[str] = None


@traceable(name="chat_retrieve", run_type="chain", project_name=CHATBOT_PROJECT)
def _chat_retrieve(question: str, thread_id: str) -> dict:
    """Retrieve documents and web results for chat (traced separately).

    Uses fast single-query search (no multi-query, no reranking) for quick responses.
    Azure AI Search semantic ranking provides good relevance without extra LLM calls.
    """
    from concurrent.futures import ThreadPoolExecutor

    route = route_query(question)
    documents = []
    web_results = []

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {}

        if route in ("vector", "hybrid"):
            # Use direct search (fast) instead of multi_query_search (slow)
            # Azure semantic ranking already provides good relevance
            # Fetch 10 results to include documents from multiple indexes
            futures["docs"] = executor.submit(search_documents, question, 10, True)

        if route in ("web", "hybrid"):
            futures["web"] = executor.submit(web_search, question, 3)

        for key, future in futures.items():
            try:
                if key == "docs":
                    documents = future.result(timeout=15)
                elif key == "web":
                    web_results = future.result(timeout=15)
            except Exception:
                pass

    context = build_context(documents, web_results)

    # Build sources list - include all fields needed for report generation
    sources = []
    for doc in documents:
        sources.append({
            "file_name": doc["file_name"],
            "document_type": doc["document_type"],
            "image_urls": doc.get("image_urls", []),
            "score": doc.get("score", 0),
            "index": doc.get("index", ""),
            "source_url": doc.get("source_url", ""),
            "type": "document",
            # Fields for report generation
            "extracted_data": doc.get("extracted_data", {}),
            "content": doc.get("content", ""),
            # c21net-specific fields (at root level)
            "monthly_rental_hkd": doc.get("monthly_rental_hkd"),
            "floor_area_sqft": doc.get("floor_area_sqft"),
            "title": doc.get("title"),  # c21net uses title instead of file_name
        })
    for r in web_results:
        if "error" not in r:
            sources.append({
                "file_name": r.get("title", "Web Result"),
                "url": r.get("url", ""),
                "type": "web",
            })

    return {"context": context, "sources": sources, "route": route}


def chat_stream(
    question: str,
    thread_id: str = None,
):
    """Streaming chat function - yields text chunks.

    Args:
        question: User's question
        thread_id: Conversation thread ID (for memory persistence)

    Yields:
        str: Text chunks as they arrive from LLM

    Returns:
        After iteration, call get_stream_metadata() to get sources
    """
    if not thread_id:
        thread_id = str(uuid.uuid4())

    # Step 1: Retrieve (traced)
    retrieval = _chat_retrieve(question, thread_id)
    context = retrieval["context"]
    sources = retrieval["sources"]

    # Store sources for retrieval after streaming
    _stream_metadata[thread_id] = StreamingChatResponse(sources=sources)

    # Step 2: Get existing conversation history
    try:
        config = {"configurable": {"thread_id": thread_id}}
        state = chatbot_graph.get_state(config)
        messages = state.values.get("messages", []) if state.values else []
    except:
        messages = []

    # Step 3: Stream LLM response (traced via @traceable on call_llm_stream)
    full_answer = []
    try:
        for chunk in call_llm_stream(question, context, messages):
            full_answer.append(chunk)
            yield chunk
    except GeneratorExit:
        # User closed the stream (navigated away, page rerun) - this is normal
        # Save partial answer to memory anyway
        answer = "".join(full_answer)
        if answer:
            try:
                config = {"configurable": {"thread_id": thread_id}}
                chatbot_graph.update_state(config, {
                    "messages": [
                        {"role": "user", "content": question},
                        {"role": "assistant", "content": answer + " [interrupted]"}
                    ]
                })
            except:
                pass
        return
    except Exception as e:
        _stream_metadata[thread_id].error = str(e)
        yield f"\n\nError: {e}"
        return

    # Step 4: Update conversation memory after streaming completes
    answer = "".join(full_answer)
    try:
        config = {"configurable": {"thread_id": thread_id}}
        chatbot_graph.update_state(
            config,
            {
                "messages": [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": answer}
                ],
                "current_question": question,
                "context": context,
                "sources": sources,
                "answer": answer,
            }
        )
    except Exception:
        pass  # Memory update failure shouldn't break chat


# Storage for streaming metadata (sources, errors)
_stream_metadata: dict[str, StreamingChatResponse] = {}


def get_stream_metadata(thread_id: str) -> StreamingChatResponse:
    """Get metadata (sources, errors) after streaming completes."""
    return _stream_metadata.pop(thread_id, StreamingChatResponse())


def get_conversation_history(thread_id: str) -> list[dict]:
    """Get conversation history for a thread.

    Args:
        thread_id: The conversation thread ID

    Returns:
        List of messages in the conversation
    """
    try:
        config = {"configurable": {"thread_id": thread_id}}
        state = chatbot_graph.get_state(config)
        return state.values.get("messages", []) if state.values else []
    except:
        return []


def clear_conversation(thread_id: str) -> bool:
    """Clear conversation history for a thread.

    Note: MemorySaver doesn't support deletion, so this creates a new empty state.

    Args:
        thread_id: The conversation thread ID

    Returns:
        True if successful
    """
    # For MemorySaver, we can't truly delete, but the thread will be forgotten
    # when the app restarts. For true persistence, use PostgresSaver.
    return True
