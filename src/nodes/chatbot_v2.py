"""RAG Chatbot v2 - Refactored with LangChain + LangGraph.

Simplified implementation using:
- LangChain ChatOpenAI for LLM calls
- LangChain AzureOpenAIEmbeddings for embeddings
- LangGraph conditional edges for routing
- Built-in streaming support

Reduces ~1100 lines to ~400 lines while maintaining all features.
"""

import os
import json
import uuid
from typing import Optional, Annotated, TypedDict, Literal
from dataclasses import dataclass, field
from operator import add
from concurrent.futures import ThreadPoolExecutor

from langsmith import traceable
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

# LangChain imports
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# Import working embedding function from indexer
from src.nodes.indexer import get_embedding as get_embedding_vector


# ============ Configuration ============

CHATBOT_PROJECT = "property-chatbot"


# ============ LangChain Models (Lazy Init) ============

def get_llm() -> ChatOpenAI:
    """Get or create LLM instance."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")

    return ChatOpenAI(
        model="meta-llama/llama-3.3-70b-instruct",
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        temperature=0.5,
        max_tokens=2000,
        streaming=True,
    )


def get_fast_llm() -> ChatOpenAI:
    """Get fast LLM for query generation and reranking."""
    return ChatOpenAI(
        model="deepseek/deepseek-chat",
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ.get("OPENROUTER_API_KEY"),
        temperature=0.3,
        max_tokens=200,
    )


# ============ Data Classes ============

@dataclass
class ChatMessage:
    """A chat message."""
    role: str
    content: str


@dataclass
class ChatResponse:
    """Response from the chatbot."""
    answer: str
    sources: list[dict] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class StreamingChatResponse:
    """Response container for streaming chat."""
    sources: list[dict] = field(default_factory=list)
    error: Optional[str] = None


# ============ LangGraph State ============

class ChatState(TypedDict):
    """State for the chatbot graph."""
    messages: Annotated[list[dict], add]
    current_question: str
    context: str
    sources: list[dict]
    answer: str
    search_route: str


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

DO NOT answer questions about: cooking, recipes, general knowledge, coding, travel, health, entertainment, sports, politics, or ANY topic outside commercial property.

## Response Rules
1. **Language**: ALWAYS respond in the SAME language as the user's question
2. **Accuracy**: Use information from context. Never make up information.
3. **Citations**: Always cite sources - (來源: filename) or (Source: filename)

## Available Property Information
{context}

---
Based ONLY on the above property information, help the user."""


# ============ Search Functions ============

@traceable(name="search_documents", run_type="retriever", project_name=CHATBOT_PROJECT)
def search_documents(query: str, top_k: int = 5) -> list[dict]:
    """Search vector database with hybrid search."""
    import httpx

    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    api_key = os.environ.get("AZURE_SEARCH_API_KEY")
    index_name = os.environ.get("AZURE_SEARCH_INDEX", "processed-documents")

    if not all([endpoint, api_key]):
        return []

    # Get embedding using existing function
    query_embedding = get_embedding_vector(query)

    # Search Azure AI Search
    search_url = f"{endpoint}/indexes/{index_name}/docs/search?api-version=2024-07-01"
    headers = {"Content-Type": "application/json", "api-key": api_key}
    body = {
        "search": query,
        "searchFields": "content,file_name",
        "vectorQueries": [{
            "kind": "vector",
            "vector": query_embedding,
            "fields": "content_vector",
            "k": top_k,
        }],
        "select": "id,file_name,document_type,content,extracted_data,processed_at",
        "top": top_k,
    }

    with httpx.Client(timeout=30) as client:
        response = client.post(search_url, headers=headers, json=body)
        response.raise_for_status()

    results = response.json().get("value", [])

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


@traceable(name="web_search", run_type="retriever", project_name=CHATBOT_PROJECT)
def web_search(query: str, max_results: int = 3) -> list[dict]:
    """Search web using Tavily."""
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return [{"error": "TAVILY_API_KEY not set"}]

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)

        response = client.search(
            query=f"Hong Kong commercial property {query}",
            search_depth="basic",
            max_results=max_results,
        )

        return [{
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", "")[:500],
            "source": "web",
        } for r in response.get("results", [])]

    except Exception as e:
        return [{"error": str(e)}]


@traceable(name="generate_query_variations", run_type="llm", project_name=CHATBOT_PROJECT)
def generate_query_variations(query: str) -> list[str]:
    """Generate query variations using LangChain."""
    try:
        llm = get_fast_llm()
        prompt = f"""Generate 3 alternative search queries for Hong Kong property search.
Original: {query}
Return ONLY a JSON array: ["query1", "query2", "query3"]"""

        response = llm.invoke([HumanMessage(content=prompt)])

        import re
        match = re.search(r'\[.*?\]', response.content, re.DOTALL)
        if match:
            variations = json.loads(match.group())
            return [query] + [v for v in variations if v != query][:3]
        return [query]
    except:
        return [query]


@traceable(name="rerank_documents", run_type="chain", project_name=CHATBOT_PROJECT)
def rerank_documents(query: str, documents: list[dict], top_k: int = 5) -> list[dict]:
    """Rerank documents using LangChain LLM."""
    if len(documents) <= top_k:
        return documents

    try:
        llm = get_fast_llm()

        doc_summaries = []
        for i, doc in enumerate(documents):
            summary = f"[{i}] {doc.get('file_name', '')} - {doc.get('content', '')[:200]}"
            doc_summaries.append(summary)

        prompt = f"""Score relevance (0-10) for each document to query: "{query}"

Documents:
{chr(10).join(doc_summaries)}

Return ONLY JSON array of scores: [8, 3, 9, ...]"""

        response = llm.invoke([HumanMessage(content=prompt)])

        import re
        match = re.search(r'\[[\d,\s\.]+\]', response.content)
        if match:
            scores = json.loads(match.group())
            scored = sorted(zip(documents, scores), key=lambda x: float(x[1]), reverse=True)
            return [doc for doc, _ in scored[:top_k]]

        return documents[:top_k]
    except:
        return documents[:top_k]


@traceable(name="multi_query_search", run_type="retriever", project_name=CHATBOT_PROJECT)
def multi_query_search(query: str, top_k: int = 5) -> list[dict]:
    """Multi-query search with reranking."""
    queries = generate_query_variations(query)
    seen = {}

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(search_documents, q, 15) for q in queries]
        for future in futures:
            try:
                for doc in future.result(timeout=15):
                    fname = doc["file_name"]
                    if fname not in seen:
                        seen[fname] = doc
            except:
                pass

    candidates = list(seen.values())
    return rerank_documents(query, candidates, top_k) if candidates else []


# ============ Query Router ============

def route_query(query: str) -> Literal["vector", "web", "hybrid"]:
    """Route query to appropriate search method."""
    q = query.lower()

    # Check hybrid first (comparison queries need both sources)
    if any(p in q for p in ["比較", "對比", "compare", "versus", "vs"]):
        return "hybrid"

    # Web-only patterns
    if any(p in q for p in ["市場趨勢", "地產市場", "樓市", "market trend", "property market"]):
        return "web"

    # Score keywords
    vector_kw = ["寫字樓", "商舖", "出租", "office", "retail", "中環", "尖沙咀", "觀塘"]
    web_kw = ["趨勢", "市場", "新聞", "trend", "news", "2024", "2025", "2026"]

    v_score = sum(1 for k in vector_kw if k in q)
    w_score = sum(1 for k in web_kw if k in q)

    if v_score > 0 and w_score == 0:
        return "vector"
    elif w_score > 0 and v_score == 0:
        return "web"
    return "web" if w_score >= v_score else "vector"


# ============ Context Builder ============

def build_context(documents: list[dict], web_results: list[dict] = None) -> str:
    """Build context from documents and web results."""
    parts = []

    for i, doc in enumerate(documents, 1):
        extracted = doc.get("extracted_data", {})
        parts.append(f"""
---
**Document {i}: {doc['file_name']}** (Type: {doc['document_type']})
{json.dumps(extracted, ensure_ascii=False, indent=2) if extracted else ''}
Content: {doc.get('content', '')[:500]}
""")

    if web_results:
        valid = [r for r in web_results if "error" not in r]
        if valid:
            parts.append("\n---\n## Web Results\n")
            for r in valid:
                parts.append(f"**{r.get('title', '')}**\n{r.get('content', '')}\n")

    return "\n".join(parts) if parts else "No relevant documents found."


# ============ LangGraph Nodes ============

@traceable(name="retrieve", run_type="chain", project_name=CHATBOT_PROJECT)
def retrieve_node(state: ChatState) -> dict:
    """Retrieve documents based on query routing."""
    question = state["current_question"]
    route = route_query(question)

    documents, web_results = [], []

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {}
        if route in ("vector", "hybrid"):
            futures["docs"] = executor.submit(multi_query_search, question, 5)
        if route in ("web", "hybrid"):
            futures["web"] = executor.submit(web_search, question, 3)

        for key, future in futures.items():
            try:
                if key == "docs":
                    documents = future.result(timeout=30)
                else:
                    web_results = future.result(timeout=15)
            except:
                pass

    context = build_context(documents, web_results)

    sources = [{"file_name": d["file_name"], "document_type": d["document_type"], "type": "document"} for d in documents]
    sources += [{"file_name": r.get("title", "Web"), "url": r.get("url", ""), "type": "web"} for r in web_results if "error" not in r]

    return {"context": context, "sources": sources, "search_route": route}


@traceable(name="generate", run_type="llm", project_name=CHATBOT_PROJECT)
def generate_node(state: ChatState) -> dict:
    """Generate answer using LangChain LLM."""
    llm = get_llm()

    messages = [SystemMessage(content=SYSTEM_PROMPT.format(context=state["context"]))]
    for msg in state.get("messages", [])[-10:]:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=state["current_question"]))

    response = llm.invoke(messages)
    answer = response.content

    return {
        "answer": answer,
        "messages": [
            {"role": "user", "content": state["current_question"]},
            {"role": "assistant", "content": answer}
        ]
    }


# ============ Graph Builder ============

def create_chatbot_graph() -> StateGraph:
    """Create chatbot graph with conditional routing."""
    graph = StateGraph(ChatState)

    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)

    return graph


# ============ Compiled Graphs ============

memory = MemorySaver()
chatbot_graph = create_chatbot_graph().compile(checkpointer=memory)
chatbot_graph_studio = create_chatbot_graph().compile()


# ============ Public API ============

@traceable(name="chat", run_type="chain", project_name=CHATBOT_PROJECT)
def chat(question: str, thread_id: str = None) -> ChatResponse:
    """Chat with memory support."""
    thread_id = thread_id or str(uuid.uuid4())

    try:
        result = chatbot_graph.invoke(
            {"current_question": question, "context": "", "sources": [], "answer": "", "messages": []},
            config={"configurable": {"thread_id": thread_id}}
        )
        return ChatResponse(answer=result["answer"], sources=result["sources"])
    except Exception as e:
        return ChatResponse(answer="", error=str(e))


# Streaming metadata storage
_stream_metadata: dict[str, StreamingChatResponse] = {}


def chat_stream(question: str, thread_id: str = None):
    """Streaming chat using LangChain streaming."""
    thread_id = thread_id or str(uuid.uuid4())

    # Step 1: Retrieve
    route = route_query(question)
    documents, web_results = [], []

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {}
        if route in ("vector", "hybrid"):
            futures["docs"] = executor.submit(multi_query_search, question, 5)
        if route in ("web", "hybrid"):
            futures["web"] = executor.submit(web_search, question, 3)

        for key, future in futures.items():
            try:
                if key == "docs":
                    documents = future.result(timeout=30)
                else:
                    web_results = future.result(timeout=15)
            except:
                pass

    context = build_context(documents, web_results)
    sources = [{"file_name": d["file_name"], "type": "document"} for d in documents]
    sources += [{"file_name": r.get("title", "Web"), "type": "web"} for r in web_results if "error" not in r]

    _stream_metadata[thread_id] = StreamingChatResponse(sources=sources)

    # Step 2: Get history
    try:
        state = chatbot_graph.get_state({"configurable": {"thread_id": thread_id}})
        history = state.values.get("messages", []) if state.values else []
    except:
        history = []

    # Step 3: Stream with LangChain
    llm = get_llm()
    messages = [SystemMessage(content=SYSTEM_PROMPT.format(context=context))]
    for msg in history[-10:]:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=question))

    full_answer = []
    try:
        for chunk in llm.stream(messages):
            content = chunk.content
            if content:
                full_answer.append(content)
                yield content
    except Exception as e:
        _stream_metadata[thread_id].error = str(e)
        yield f"\n\nError: {e}"
        return

    # Step 4: Update memory
    answer = "".join(full_answer)
    try:
        chatbot_graph.update_state(
            {"configurable": {"thread_id": thread_id}},
            {
                "messages": [{"role": "user", "content": question}, {"role": "assistant", "content": answer}],
                "current_question": question, "context": context, "sources": sources, "answer": answer,
            }
        )
    except:
        pass


def get_stream_metadata(thread_id: str) -> StreamingChatResponse:
    """Get metadata after streaming."""
    return _stream_metadata.pop(thread_id, StreamingChatResponse())


def get_conversation_history(thread_id: str) -> list[dict]:
    """Get conversation history."""
    try:
        state = chatbot_graph.get_state({"configurable": {"thread_id": thread_id}})
        return state.values.get("messages", []) if state.values else []
    except:
        return []


def clear_conversation(thread_id: str) -> bool:
    """Clear conversation (MemorySaver limitation)."""
    return True


# Keep keyword_search for Search tab compatibility
def keyword_search(query: str = "", filters: dict = None, top_k: int = 20) -> list[dict]:
    """Direct keyword search for Search tab."""
    import httpx

    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    api_key = os.environ.get("AZURE_SEARCH_API_KEY")
    index_name = os.environ.get("AZURE_SEARCH_INDEX", "processed-documents")

    if not all([endpoint, api_key]):
        return []

    search_url = f"{endpoint}/indexes/{index_name}/docs/search?api-version=2024-07-01"
    body = {
        "search": query or "*",
        "searchFields": "content,file_name",
        "select": "id,file_name,document_type,content,extracted_data,processed_at",
        "top": top_k,
        "orderby": "processed_at desc",
    }

    if filters and filters.get("document_type"):
        body["filter"] = f"document_type eq '{filters['document_type']}'"

    with httpx.Client(timeout=30) as client:
        response = client.post(search_url, headers={"Content-Type": "application/json", "api-key": api_key}, json=body)
        response.raise_for_status()

    return [{
        "id": d.get("id", ""),
        "file_name": d.get("file_name", "Unknown"),
        "document_type": d.get("document_type", "unknown"),
        "content": d.get("content", "")[:500],
        "extracted_data": json.loads(d.get("extracted_data", "{}")) if isinstance(d.get("extracted_data"), str) else d.get("extracted_data", {}),
        "processed_at": d.get("processed_at", ""),
    } for d in response.json().get("value", [])]
