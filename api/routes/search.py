"""Search endpoint — keyword + hybrid search across all indexes.

Supports two auth schemes:
- Bearer JWT  : dashboard and internal callers
- X-API-Key   : external callers (e.g. zo computer)
"""

import os
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel

from api.auth import get_current_user

router = APIRouter(prefix="/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str = ""
    top_k: int = 20
    search_type: Literal["keyword", "hybrid", "vector"] = "keyword"
    filters: dict | None = None


def _api_key_auth(x_api_key: str | None = Header(default=None)) -> str | None:
    """Validate X-API-Key header. Returns the key if valid, None if not present."""
    expected = os.environ.get("SEARCH_API_KEY")
    if not expected:
        return None
    if x_api_key == expected:
        return x_api_key
    return None


async def _require_auth(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> str:
    """Accept either a valid Bearer JWT or a valid X-API-Key. Reject if neither."""
    # Try X-API-Key first (no overhead if not present)
    expected_key = os.environ.get("SEARCH_API_KEY")
    if expected_key and x_api_key == expected_key:
        return "api-key"

    # Fall back to JWT
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        from fastapi.security import HTTPAuthorizationCredentials
        from api.auth import get_current_user, bearer_scheme
        try:
            creds = HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=auth_header[7:]
            )
            return get_current_user(creds)
        except HTTPException:
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Provide a valid Bearer token or X-API-Key header",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _format_results(raw: list[dict], search_type: str) -> list[dict]:
    return [
        {
            "file_name": d.get("file_name", ""),
            "document_type": d.get("document_type", ""),
            "score": d.get("reranker_score") or d.get("score", 0),
            "extracted_data": d.get("extracted_data", {}),
            "content_preview": d.get("content", "")[:300],
            "source_index": d.get("index", ""),
        }
        for d in raw
    ]


@router.post("")
async def search(
    body: SearchRequest,
    caller: Annotated[str, Depends(_require_auth)],
):
    """Search across all configured Azure AI Search indexes.

    Auth: Bearer JWT (dashboard) or X-API-Key header (external callers).
    """
    from src.nodes.chatbot import keyword_search, search_documents

    if body.search_type == "keyword":
        raw = keyword_search(query=body.query, filters=body.filters, top_k=body.top_k)
    else:
        hybrid = body.search_type in ("hybrid", "vector")
        raw = search_documents(query=body.query, top_k=body.top_k, hybrid=hybrid)

    results = _format_results(raw, body.search_type)
    return {
        "query": body.query,
        "search_type": body.search_type,
        "total": len(results),
        "results": results,
    }
