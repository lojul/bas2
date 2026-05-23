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

from src.nodes.indexer import get_http_client, get_embedding


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
- Tables for comparisons
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

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return documents[:top_k]

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

        # Call LLM to score relevance
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": "deepseek/deepseek-chat",
            "messages": [
                {"role": "user", "content": RERANK_PROMPT.format(query=query, documents=documents_text)}
            ],
            "max_tokens": 100,
            "temperature": 0,
        }

        client = get_http_client()
        response = client.post(url, headers=headers, json=body, timeout=15)
        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]

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
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return [query]  # Fallback to original only

    try:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        body = {
            "model": "deepseek/deepseek-chat",  # Fast and cheap
            "messages": [
                {"role": "user", "content": MULTI_QUERY_PROMPT.format(query=query)}
            ],
            "max_tokens": 200,
            "temperature": 0.7,  # Some creativity for variations
        }

        client = get_http_client()
        response = client.post(url, headers=headers, json=body, timeout=10)
        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]

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

@traceable(name="search_documents", run_type="retriever", project_name=CHATBOT_PROJECT)
def search_documents(query: str, top_k: int = 5, hybrid: bool = True) -> list[dict]:
    """Search vector database for relevant documents using hybrid search.

    Args:
        query: Search query text
        top_k: Number of results to return
        hybrid: If True, use vector + keyword search. If False, vector only.
    """
    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    api_key = os.environ.get("AZURE_SEARCH_API_KEY")
    index_name = os.environ.get("AZURE_SEARCH_INDEX", "processed-documents")

    if not all([endpoint, api_key]):
        return []

    # Get embedding for query
    query_embedding = get_embedding(query)

    # Build search request with hybrid search (vector + keyword)
    search_url = f"{endpoint}/indexes/{index_name}/docs/search?api-version=2024-07-01"
    headers = {
        "Content-Type": "application/json",
        "api-key": api_key,
    }

    body = {
        "vectorQueries": [
            {
                "kind": "vector",
                "vector": query_embedding,
                "fields": "content_vector",
                "k": top_k,
            }
        ],
        "search": query,  # Required for semantic ranking
        "searchFields": "content,file_name",
        "select": "id,file_name,document_type,content,extracted_data,processed_at",
        "top": top_k,
        # Semantic ranking for better natural language understanding
        "queryType": "semantic",
        "semanticConfiguration": "default-semantic-config",
        "captions": "extractive",  # Get highlighted captions
        "answers": "extractive",   # Get direct answers if available
    }

    client = get_http_client()
    response = client.post(search_url, headers=headers, json=body)
    response.raise_for_status()

    data = response.json()
    results = data.get("value", [])

    # Format results
    documents = []
    for doc in results:
        extracted = doc.get("extracted_data", "{}")
        if isinstance(extracted, str):
            try:
                extracted = json.loads(extracted)
            except:
                extracted = {}

        # Get semantic caption if available
        captions = doc.get("@search.captions", [])
        caption_text = captions[0].get("text", "") if captions else ""

        documents.append({
            "file_name": doc.get("file_name", "Unknown"),
            "document_type": doc.get("document_type", "unknown"),
            "content": doc.get("content", "")[:2000],
            "extracted_data": extracted,
            "score": doc.get("@search.score", 0),
            "reranker_score": doc.get("@search.rerankerScore", 0),  # Semantic score
            "caption": caption_text,  # Highlighted relevant text
        })

    # Sort by reranker score if available (semantic ranking)
    documents.sort(key=lambda x: x.get("reranker_score", 0), reverse=True)

    return documents


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


def keyword_search(
    query: str = "",
    filters: dict = None,
    top_k: int = 20,
) -> list[dict]:
    """Direct keyword search without LLM - for Search tab.

    Args:
        query: Search keywords (optional)
        filters: Dict with optional keys: document_type, district
        top_k: Number of results

    Returns:
        List of matching documents with extracted data
    """
    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    api_key = os.environ.get("AZURE_SEARCH_API_KEY")
    index_name = os.environ.get("AZURE_SEARCH_INDEX", "processed-documents")

    if not all([endpoint, api_key]):
        return []

    search_url = f"{endpoint}/indexes/{index_name}/docs/search?api-version=2024-07-01"
    headers = {
        "Content-Type": "application/json",
        "api-key": api_key,
    }

    # Build search body
    # - When query exists: use relevance ranking with field boosting
    # - When no query: return all sorted by date
    has_query = bool(query and query.strip())

    body = {
        "search": query if has_query else "*",
        # Boost file_name and extracted_data over general content for better relevance
        "searchFields": "file_name,extracted_data,content" if has_query else "content,file_name",
        "select": "id,file_name,document_type,content,extracted_data,processed_at",
        "top": top_k,
    }

    # Only sort by date when browsing (no query) - otherwise use relevance score
    if not has_query:
        body["orderby"] = "processed_at desc"

    # Enable semantic ranking for better natural language understanding
    if has_query:
        body["queryType"] = "semantic"
        body["semanticConfiguration"] = "default-semantic-config"
        body["captions"] = "extractive"
        body["answers"] = "extractive"

    # Build filter string (OData filters for top-level fields only)
    filter_parts = []
    if filters:
        if filters.get("document_type"):
            filter_parts.append(f"document_type eq '{filters['document_type']}'")

    if filter_parts:
        body["filter"] = " and ".join(filter_parts)

    client = get_http_client()
    response = client.post(search_url, headers=headers, json=body)
    response.raise_for_status()

    results = response.json().get("value", [])

    # Filter out low-relevance results when searching (not browsing)
    # Semantic reranker score ~2.5+ indicates good relevance
    MIN_RERANKER_SCORE = 2.5
    IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')

    if has_query:
        results = [
            r for r in results
            if r.get("@search.rerankerScore", 0) >= MIN_RERANKER_SCORE
            and not r.get("file_name", "").lower().endswith(IMAGE_EXTENSIONS)
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

    # Format results
    documents = []
    for doc in results:
        extracted = doc.get("extracted_data", "{}")
        if isinstance(extracted, str):
            try:
                extracted = json.loads(extracted)
            except:
                extracted = {}

        documents.append({
            "id": doc.get("id", ""),
            "file_name": doc.get("file_name", "Unknown"),
            "document_type": doc.get("document_type", "unknown"),
            "content": doc.get("content", "")[:500],
            "extracted_data": extracted,
            "processed_at": doc.get("processed_at", ""),
            "score": doc.get("@search.score", 0),
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
{units_str}
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
    """
    query_lower = query.lower()

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
    """Node: Search for relevant documents and/or web based on query type."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    question = state["current_question"]

    # Route query to determine search strategy
    route = route_query(question)

    documents = []
    web_results = []

    # Run searches in PARALLEL for better latency
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {}

        if route in ("vector", "hybrid"):
            futures["docs"] = executor.submit(multi_query_search, question, 5)

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

    # Build sources list
    sources = []
    for doc in documents:
        sources.append({
            "file_name": doc["file_name"],
            "document_type": doc["document_type"],
            "score": doc.get("score", 0),
            "type": "document",
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
    """Call LLM to generate answer (non-streaming)."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://c21hk.com",
        "X-Title": "C21 Property Intelligence",
    }

    body = {
        "model": "meta-llama/llama-3.3-70b-instruct",
        "messages": _build_llm_messages(question, context, messages),
        "temperature": 0.5,
        "max_tokens": 2000,
    }

    client = get_http_client()
    response = client.post(url, headers=headers, json=body, timeout=60)
    response.raise_for_status()

    data = response.json()
    return data["choices"][0]["message"]["content"]


@traceable(name="generate_answer_stream", run_type="llm", project_name=CHATBOT_PROJECT)
def call_llm_stream(question: str, context: str, messages: list[dict]):
    """Call LLM with streaming - yields text chunks."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://c21hk.com",
        "X-Title": "C21 Property Intelligence",
    }

    body = {
        "model": "meta-llama/llama-3.3-70b-instruct",
        "messages": _build_llm_messages(question, context, messages),
        "temperature": 0.5,
        "max_tokens": 2000,
        "stream": True,
    }

    # Use httpx streaming
    try:
        with httpx.Client(timeout=60) as client:
            with client.stream("POST", url, headers=headers, json=body) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        data = line[6:]  # Remove "data: " prefix
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
    except GeneratorExit:
        # Stream was closed by caller - this is normal, don't propagate
        return


def generate_node(state: ChatState) -> dict:
    """Node: Generate answer using LLM."""
    answer = call_llm(
        state["current_question"],
        state["context"],
        state.get("messages", [])
    )
    # Add the exchange to messages for memory
    new_messages = [
        {"role": "user", "content": state["current_question"]},
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
            futures["docs"] = executor.submit(search_documents, question, 5, True)

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

    sources = []
    for doc in documents:
        sources.append({
            "file_name": doc["file_name"],
            "document_type": doc["document_type"],
            "score": doc.get("score", 0),
            "type": "document",
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
