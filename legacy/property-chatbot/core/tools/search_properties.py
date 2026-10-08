"""Hybrid + semantic search against BAS's properties-index. Read-only.

Same query shape as business-automation-system/ai-agent's own search_properties
tool: vector (contentVector) + keyword (BM25) hybrid, Azure semantic reranker
with extractive captions on the "default" semantic configuration (confirmed
live on the index — no changes needed there).
"""

from azure.search.documents.models import VectorizedQuery
from langchain_core.tools import tool

from core.azure_clients import embed, search_client


def _format_result(doc: dict) -> str:
    parts = [f"- {doc.get('address') or '(no address)'}"]
    if doc.get("district"):
        parts.append(f"District: {doc['district']}")
    if doc.get("propertyType"):
        parts.append(f"Type: {doc['propertyType']}")
    if doc.get("transactionType"):
        parts.append(f"Transaction: {doc['transactionType']}")
    if doc.get("price"):
        parts.append(f"Price: HK${doc['price']:,.0f}/month")
    if doc.get("area_sqft"):
        parts.append(f"Size: {doc['area_sqft']:,.0f} sq ft")
    if doc.get("agentName"):
        parts.append(f"Agent: {doc['agentName']}")
    caption = doc.get("@search.captions")
    if caption:
        parts.append(f"Excerpt: {caption[0].text}")
    return " | ".join(parts)


def run_search(query: str, top_k: int = 5) -> list[dict]:
    """Callable directly (not just as an LLM tool) — e.g. for tests."""
    vector = embed(query)
    results = search_client.search(
        search_text=query,
        vector_queries=[
            VectorizedQuery(vector=vector, k_nearest_neighbors=top_k, fields="contentVector")
        ],
        query_type="semantic",
        semantic_configuration_name="default",
        query_caption="extractive",
        highlight_fields="content,address",
        top=top_k,
    )
    return [dict(r) for r in results]


@tool
def search_properties(query: str, top_k: int = 5) -> str:
    """Search Hong Kong commercial property listings by district, type, size, or rent.

    Use this whenever the user asks about specific properties, districts, or
    availability. Returns a formatted list of matching listings, or a message
    if nothing matches.
    """
    docs = run_search(query, top_k)
    if not docs:
        return "No matching properties found."
    return "\n".join(_format_result(d) for d in docs)
