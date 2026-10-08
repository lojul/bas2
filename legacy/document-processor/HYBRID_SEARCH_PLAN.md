# RAG Chatbot Enhancement Plan

## Overview
Enhance the RAG chatbot with:
1. **Hybrid Search** - Vector DB + Web Search
2. **Tool-Calling Agent** - Generate PDFs, PowerPoints
3. **Advanced RAG** - Reranking, multi-query retrieval

## Technology Stack

| Component | Current | Future |
|-----------|---------|--------|
| Workflow | LangGraph | LangGraph (keep) |
| LLM Calls | Direct API (httpx) | **LangChain** (for tools) |
| Retrieval | Direct API | **LangChain Retrievers** (advanced RAG) |
| Tools | None | **LangChain Tools** (web, PDF, PPT) |

## What is RAG?

**RAG = Retrieval Augmented Generation**
```
Question → RETRIEVE docs → AUGMENT prompt → GENERATE answer
```

Our chatbot IS a RAG system. LangChain helps build better RAG.

## What LangChain Adds (Chat/RAG Only)

| Feature | Without LangChain | With LangChain |
|---------|-------------------|----------------|
| Web search | Manual Tavily API | `@tool` decorator |
| PDF generation | Manual code | `@tool` decorator |
| Multi-query RAG | Build yourself | `MultiQueryRetriever` |
| Reranking | Build yourself | `CohereRerank` |
| Tool calling | Complex | `create_tool_calling_agent()` |

**Note:** LangChain is for RAG/chatbot only. Document processing (OCR, classify, extract) stays with Azure Document Intelligence + direct API.

---

## Phase 1: Hybrid Search (No LangChain Yet)

## Current Graph
```
START → retrieve → generate → END
```

## Enhanced Graph (Option A: Parallel)
```
                    ┌─────────────────┐
                    │  vector_search  │ (Azure AI Search)
                    └────────┬────────┘
START → retrieve_router ─────┼─────────→ merge_results → generate → END
                    ┌────────┴────────┐
                    │   web_search    │ (Tavily)
                    └─────────────────┘
```

## Enhanced Graph (Option B: Smart Router)
```
START → analyze_query → router ─┬─→ vector_only ────→ generate → END
                                ├─→ web_only ───────→ generate → END
                                └─→ hybrid_search ──→ generate → END
```

**Router decides based on query:**
- "中環寫字樓" → Vector only (property search)
- "香港商業地產市場新聞" → Web only (news/trends)
- "比較中環租金同最新市場走勢" → Hybrid (both)

## Recommended: Option A (Parallel) with Smart Merge

Simpler to implement, always gets both sources, LLM decides relevance.

## New Graph Structure

```python
class ChatState(TypedDict):
    messages: list[dict]
    current_question: str
    vector_results: list[dict]    # NEW
    web_results: list[dict]       # NEW
    context: str
    sources: list[dict]
    answer: str

# Nodes
def vector_search_node(state) -> dict:
    """Search Azure AI Search (existing logic)"""

def web_search_node(state) -> dict:
    """Search Tavily for web results"""

def merge_results_node(state) -> dict:
    """Combine vector + web results into context"""

def generate_node(state) -> dict:
    """Generate answer using merged context"""
```

## New Graph Definition

```python
from langgraph.graph import StateGraph, START, END

def create_hybrid_chatbot_graph():
    graph = StateGraph(ChatState)

    # Add nodes
    graph.add_node("vector_search", vector_search_node)
    graph.add_node("web_search", web_search_node)
    graph.add_node("merge_results", merge_results_node)
    graph.add_node("generate", generate_node)

    # Parallel search: START fans out to both searches
    graph.add_edge(START, "vector_search")
    graph.add_edge(START, "web_search")

    # Both searches merge
    graph.add_edge("vector_search", "merge_results")
    graph.add_edge("web_search", "merge_results")

    # Generate from merged results
    graph.add_edge("merge_results", "generate")
    graph.add_edge("generate", END)

    return graph
```

## Implementation Steps

### Step 1: Set Up Tavily
1. Sign up at https://tavily.com (free tier: 1,000 searches/month)
2. Get API key
3. Add to Streamlit secrets: `TAVILY_API_KEY = "tvly-xxx"`

### Step 2: Create Web Search Node
```python
from tavily import TavilyClient

def web_search_node(state: ChatState) -> dict:
    """Search web for relevant information."""
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return {"web_results": []}

    client = TavilyClient(api_key=api_key)

    # Add Hong Kong property context to query
    query = f"Hong Kong commercial property {state['current_question']}"

    response = client.search(
        query=query,
        search_depth="basic",
        max_results=3,
        include_domains=["scmp.com", "hk01.com", "property.hk"],  # Optional: limit sources
    )

    web_results = [
        {
            "title": r["title"],
            "url": r["url"],
            "content": r["content"][:500],
            "source": "web"
        }
        for r in response["results"]
    ]

    return {"web_results": web_results}
```

### Step 3: Create Merge Node
```python
def merge_results_node(state: ChatState) -> dict:
    """Merge vector and web results into unified context."""
    vector_results = state.get("vector_results", [])
    web_results = state.get("web_results", [])

    context_parts = []
    sources = []

    # Add vector results (property documents)
    if vector_results:
        context_parts.append("## Property Documents (Internal Database)")
        for doc in vector_results:
            context_parts.append(f"**{doc['file_name']}**\n{doc['content'][:500]}")
            sources.append({"name": doc["file_name"], "type": "document"})

    # Add web results (internet)
    if web_results:
        context_parts.append("\n## Web Search Results (Latest Information)")
        for r in web_results:
            context_parts.append(f"**{r['title']}**\nSource: {r['url']}\n{r['content']}")
            sources.append({"name": r["title"], "type": "web", "url": r["url"]})

    return {
        "context": "\n\n".join(context_parts),
        "sources": sources
    }
```

### Step 4: Update System Prompt
Add instructions for handling web sources:
```
## Source Types
You have access to two types of information:
1. **Internal Documents**: Property listings, contacts from our database
2. **Web Results**: Latest news and market information from the internet

When citing sources:
- Documents: (Source: filename.pdf)
- Web: (Source: Article Title - website.com)

Prioritize internal documents for specific property details.
Use web results for market trends, news, and general information.
```

### Step 5: Update Dashboard
Show web sources differently in chat:
```python
# In render_chat_tab()
for src in sources:
    if src.get("type") == "web":
        st.write(f"🌐 [{src['name']}]({src['url']})")
    else:
        st.write(f"📄 {src['name']}")
```

## Files to Modify

| File | Changes |
|------|---------|
| `src/nodes/chatbot.py` | Add web_search_node, merge_results_node, update graph |
| `dashboard.py` | Update sources display for web links |
| `streamlit_secrets.txt` | Add TAVILY_API_KEY |
| `CLAUDE.md` | Document hybrid search feature |

## Cost Impact

| Component | Per Query | Monthly (500 queries) |
|-----------|-----------|----------------------|
| Tavily (free tier) | $0 | $0 (1000 free) |
| Tavily (paid) | $0.001 | $0.50 |
| Azure AI Search | included | $70 |
| OpenRouter LLM | $0.003 | $1.50 |
| **Total** | ~$0.004 | ~$72 |

## Testing Plan

1. Test vector-only query: "Show me offices in Central"
2. Test web-relevant query: "Latest HK property market news"
3. Test hybrid query: "Compare Central office rents with market trends"
4. Verify sources display correctly (document vs web)

---

# Phase 2: Tool-Calling Agent (Add LangChain)

## Overview
Add LangChain to enable tool-calling agent that can:
- Search the web
- Generate PDF reports
- Generate PowerPoint presentations

## Install LangChain
```bash
pip install langchain langchain-openai langchain-community
```

## New Architecture

```
User Question
      ↓
┌─────────────────────────────────────────┐
│         LangChain Agent                 │
│   (decides which tools to use)          │
│                                         │
│   ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│   │ Vector  │ │   Web   │ │ Generate│  │
│   │ Search  │ │ Search  │ │ PDF/PPT │  │
│   └─────────┘ └─────────┘ └─────────┘  │
│                                         │
└─────────────────────────────────────────┘
      ↓
Answer + Generated Files
```

## Implementation

### Define Tools
```python
from langchain.tools import tool
from langchain_openai import ChatOpenAI

@tool
def search_properties(query: str) -> str:
    """Search internal property database for listings."""
    # Existing vector search logic
    results = search_documents(query)
    return format_results(results)

@tool
def search_web(query: str) -> str:
    """Search the web for latest property news and market trends."""
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    results = client.search(f"Hong Kong property {query}", max_results=3)
    return format_web_results(results)

@tool
def generate_pdf_report(property_ids: list[str]) -> str:
    """Generate a PDF report for selected properties.

    Args:
        property_ids: List of property IDs to include in report

    Returns:
        URL to download the generated PDF
    """
    # Generate PDF logic
    pdf_url = create_property_report_pdf(property_ids)
    return f"PDF report generated: {pdf_url}"

@tool
def generate_powerpoint(property_ids: list[str], title: str) -> str:
    """Generate a PowerPoint presentation for selected properties.

    Args:
        property_ids: List of property IDs to include
        title: Presentation title

    Returns:
        URL to download the generated PowerPoint
    """
    # Generate PPT logic
    ppt_url = create_property_presentation(property_ids, title)
    return f"PowerPoint generated: {ppt_url}"
```

### Create Agent
```python
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate

# Define tools
tools = [search_properties, search_web, generate_pdf_report, generate_powerpoint]

# Create prompt
prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a Property Intelligence Assistant for Century 21 Hong Kong.

You have access to these tools:
- search_properties: Search internal database for property listings
- search_web: Search internet for latest news and market trends
- generate_pdf_report: Create PDF report of properties
- generate_powerpoint: Create presentation of properties

Always search for relevant properties first before generating reports.
Respond in the same language as the user (Chinese or English)."""),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

# Create agent
llm = ChatOpenAI(model="gpt-4", temperature=0)
agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
```

### Example Usage
```python
# User asks for a report
response = agent_executor.invoke({
    "input": "Find offices in Central under 50k and create a PDF report"
})

# Agent will:
# 1. Call search_properties("offices Central under 50000")
# 2. Get property IDs from results
# 3. Call generate_pdf_report(property_ids)
# 4. Return answer with PDF link
```

## PDF Generation (python-pptx, reportlab)
```bash
pip install reportlab python-pptx
```

```python
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

def create_property_report_pdf(property_ids: list[str]) -> str:
    """Generate PDF report for properties."""
    # Fetch property data
    properties = get_properties_by_ids(property_ids)

    # Create PDF
    filename = f"report_{uuid.uuid4().hex[:8]}.pdf"
    filepath = f"/tmp/{filename}"

    c = canvas.Canvas(filepath, pagesize=letter)
    c.drawString(100, 750, "Property Report - Century 21")

    y = 700
    for prop in properties:
        c.drawString(100, y, f"Building: {prop['building_name']}")
        c.drawString(100, y-15, f"Address: {prop['address']}")
        c.drawString(100, y-30, f"Size: {prop['size']} sqft | Rent: HK${prop['rent']}")
        y -= 60

    c.save()

    # Upload to blob storage and return URL
    url = upload_to_blob(filepath, filename)
    return url
```

## Files to Modify

| File | Changes |
|------|---------|
| `src/nodes/chatbot.py` | Add LangChain agent, tools |
| `src/tools/pdf_generator.py` | New - PDF generation |
| `src/tools/ppt_generator.py` | New - PowerPoint generation |
| `requirements.txt` | Add langchain, reportlab, python-pptx |

---

# Phase 3: Advanced RAG (LangChain Retrievers)

## Overview
Improve retrieval quality with LangChain's advanced RAG patterns.

## Features to Add

### 1. Multi-Query Retrieval
Generate multiple versions of the question to improve recall.

```python
from langchain.retrievers import MultiQueryRetriever

retriever = MultiQueryRetriever.from_llm(
    retriever=base_retriever,
    llm=llm
)

# User asks: "中環寫字樓"
# LLM generates:
# - "Central district office space for rent"
# - "Commercial property in Central Hong Kong"
# - "Office listings Central area"
# Searches all 3, combines results
```

### 2. Contextual Compression (Reranking)
Rerank results to put most relevant first.

```python
from langchain.retrievers import ContextualCompressionRetriever
from langchain_cohere import CohereRerank

compressor = CohereRerank(top_n=5)
compression_retriever = ContextualCompressionRetriever(
    base_compressor=compressor,
    base_retriever=retriever
)
```

### 3. Self-Query Retrieval
Extract filters from natural language.

```python
from langchain.retrievers import SelfQueryRetriever

# User: "offices in Central under 50k"
# Extracts:
#   - query: "offices"
#   - filter: district="Central", rent<50000
```

## Cost Considerations

| Feature | Additional Cost |
|---------|----------------|
| Multi-Query | 3x LLM calls for query generation |
| Cohere Rerank | $1 per 1000 searches |
| Self-Query | 1 extra LLM call for filter extraction |

---

# Summary: Three Phases

| Phase | Features | LangChain? | Complexity |
|-------|----------|------------|------------|
| **1** | Hybrid search (Vector + Web) | No | Low |
| **2** | Tool-calling agent (PDF, PPT) | **Yes** | Medium |
| **3** | Advanced RAG (rerank, multi-query) | **Yes** | High |

## Recommended Order
1. ✅ Phase 1 first - adds web search, no new dependencies
2. 📋 Phase 2 next - adds real value (PDF/PPT generation)
3. 📋 Phase 3 last - optimization, only if retrieval quality is an issue

---

## Future Enhancements

- [ ] Add query router (smart decide: vector/web/both)
- [ ] Add source quality ranking
- [ ] Cache web results (avoid duplicate searches)
- [ ] Add more web sources (Google News API, RSS feeds)
- [ ] Filter web results by date (only recent news)
- [ ] Add email tool (send property info to clients)
- [ ] Add calendar tool (schedule viewings)
- [ ] Add CRM integration (log interactions)
