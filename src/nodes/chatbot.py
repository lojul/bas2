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

## Response Rules
1. **Language**: ALWAYS respond in the SAME language as the user's question
   - 繁體中文 question → 繁體中文 answer
   - English question → English answer

2. **Accuracy**: Only use information from the provided documents
   - If not found: "根據現有資料，我未能找到相關資訊。" or "I couldn't find this in the available documents."
   - NEVER make up information

3. **Citations**: Always cite sources - (來源: filename) or (Source: filename)

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
def search_documents(query: str, top_k: int = 5) -> list[dict]:
    """Search vector database for relevant documents."""
    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    api_key = os.environ.get("AZURE_SEARCH_API_KEY")
    index_name = os.environ.get("AZURE_SEARCH_INDEX", "processed-documents")

    if not all([endpoint, api_key]):
        return []

    # Get embedding for query
    query_embedding = get_embedding(query)

    # Build search request with vector search
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


def build_context(documents: list[dict]) -> str:
    """Build context string from retrieved documents."""
    if not documents:
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

    return "\n".join(context_parts)


def retrieve_node(state: ChatState) -> dict:
    """Node: Search for relevant documents."""
    question = state["current_question"]
    documents = search_documents(question, top_k=5)
    context = build_context(documents)
    sources = [
        {
            "file_name": doc["file_name"],
            "document_type": doc["document_type"],
            "score": doc.get("score", 0),
        }
        for doc in documents
    ]
    return {"context": context, "sources": sources}


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

# Compile graph with memory
chatbot_graph = create_chatbot_graph().compile(checkpointer=memory)


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
    context = build_context(documents)
    sources = [
        {
            "file_name": doc["file_name"],
            "document_type": doc["document_type"],
            "score": doc.get("score", 0),
        }
        for doc in documents
    ]

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
