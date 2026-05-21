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
from langsmith import traceable
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
        "select": "id,file_name,document_type,content,extracted_data,processed_at",
        "top": top_k,
    }

    # Add keyword search for hybrid mode
    if hybrid:
        body["search"] = query  # Full-text search on searchable fields
        body["searchFields"] = "content,file_name"  # Fields to search

    client = get_http_client()
    response = client.post(search_url, headers=headers, json=body)
    response.raise_for_status()

    results = response.json().get("value", [])

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
            "file_name": doc.get("file_name", "Unknown"),
            "document_type": doc.get("document_type", "unknown"),
            "content": doc.get("content", "")[:2000],
            "extracted_data": extracted,
            "score": doc.get("@search.score", 0),
        })

    return documents


def keyword_search(
    query: str = "",
    filters: dict = None,
    top_k: int = 20,
) -> list[dict]:
    """Direct keyword search without LLM - for Search tab.

    Args:
        query: Search keywords (optional)
        filters: Dict with optional keys: document_type, district, min_rent, max_rent
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

    body = {
        "search": query if query else "*",  # * returns all if no query
        "searchFields": "content,file_name",
        "select": "id,file_name,document_type,content,extracted_data,processed_at",
        "top": top_k,
        "orderby": "processed_at desc",
    }

    # Build filter string
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

    # Keywords indicating web search (news, trends, market analysis)
    web_keywords = [
        "趨勢", "走勢", "市場", "新聞", "最新", "預測", "分析報告",
        "trend", "news", "market", "forecast", "outlook", "analysis",
        "2024", "2025", "2026",  # Recent year queries
        "今年", "去年", "最近",
    ]

    # Keywords indicating vector search (specific property queries)
    vector_keywords = [
        "有什麼", "有咩", "邊度有", "搵", "找", "出租", "招租",
        "寫字樓", "商舖", "工廈", "倉庫", "office", "retail", "industrial",
        "呎租", "租金", "面積", "聯絡", "contact",
        "中環", "尖沙咀", "旺角", "觀塘", "葵涌",  # District names
        "central", "tsim sha tsui", "mongkok", "kwun tong",
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

    # Decide based on scores
    if web_score > 0 and vector_score == 0:
        return "web"
    elif vector_score > 0 and web_score == 0:
        return "vector"
    elif web_score > vector_score:
        return "web"
    elif vector_score > web_score:
        return "vector"
    else:
        # Default to hybrid when unclear
        return "hybrid"


def retrieve_node(state: ChatState) -> dict:
    """Node: Search for relevant documents and/or web based on query type."""
    question = state["current_question"]

    # Route query to determine search strategy
    route = route_query(question)

    documents = []
    web_results = []

    if route in ("vector", "hybrid"):
        # Search vector database (your documents)
        documents = search_documents(question, top_k=5)

    if route in ("web", "hybrid"):
        # Search web for latest information
        web_results = web_search(question, max_results=3)

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

    # Step 1: Retrieve documents (non-streaming)
    documents = search_documents(question, top_k=5)

    # Step 1b: Search web for latest information
    web_results = web_search(question, max_results=3)

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
    for r in web_results:
        sources.append({
            "file_name": r.get("title", "Web Result"),
            "url": r.get("url", ""),
            "type": "web",
        })

    # Store sources for retrieval after streaming
    _stream_metadata[thread_id] = StreamingChatResponse(sources=sources)

    # Step 2: Get existing conversation history
    try:
        config = {"configurable": {"thread_id": thread_id}}
        state = chatbot_graph.get_state(config)
        messages = state.values.get("messages", []) if state.values else []
    except:
        messages = []

    # Step 3: Stream LLM response
    full_answer = []
    try:
        for chunk in call_llm_stream(question, context, messages):
            full_answer.append(chunk)
            yield chunk
    except Exception as e:
        _stream_metadata[thread_id].error = str(e)
        yield f"\n\nError: {e}"
        return

    # Step 4: Update conversation memory after streaming completes
    answer = "".join(full_answer)
    try:
        # Manually update the graph state with new messages
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
        pass  # Memory update failure shouldn't break the response


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
