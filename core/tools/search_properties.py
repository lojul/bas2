"""Hybrid + semantic search against BAS's properties-index. Read-only.

Same query shape as business-automation-system/ai-agent's own search_properties tool
(semantic_configuration_name="default", which exists on the live index — confirmed).
"""

from langchain_core.tools import tool

# TODO: real implementation — SearchClient + DefaultAzureCredential
# (Search Index Data Reader role), embed the query via BAS_OPENAI_ENDPOINT,
# vector + keyword hybrid search, semantic rerank, return top_k formatted results.


@tool
def search_properties(query: str, top_k: int = 5) -> str:
    """Search Hong Kong commercial property listings by district, type, size, or rent.

    Use this whenever the user asks about specific properties, districts, or
    availability. Not yet implemented — scaffold only.
    """
    return "search_properties: not yet implemented"
