"""Search endpoint — keyword + hybrid search across all indexes."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import get_current_user

router = APIRouter(prefix="/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str = ""
    top_k: int = 20
    search_type: Literal["keyword", "hybrid", "vector"] = "keyword"
    filters: dict | None = None


@router.post("")
def search(
    body: SearchRequest,
    username: Annotated[str, Depends(get_current_user)],
):
    """Search across all configured Azure AI Search indexes."""
    from src.nodes.chatbot import keyword_search, search_documents

    if body.search_type == "keyword":
        results = keyword_search(
            query=body.query,
            filters=body.filters,
            top_k=body.top_k,
        )
    else:
        hybrid = body.search_type in ("hybrid", "vector")
        results = search_documents(
            query=body.query,
            top_k=body.top_k,
            hybrid=hybrid,
        )

    return {"query": body.query, "search_type": body.search_type, "total": len(results), "results": results}
