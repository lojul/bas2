"""Azure AI Search indexer for processed documents."""

import os
import json
import hashlib
from datetime import datetime, timezone
from typing import Optional

import httpx
from langsmith import traceable

from src.state import DocumentState, ProcessingStatus


# Text limit for content/embeddings
MAX_CONTENT_LENGTH = 8000

# Index schema for auto-creation
INDEX_SCHEMA = {
    "name": "processed-documents",
    "fields": [
        {"name": "id", "type": "Edm.String", "key": True, "searchable": False},
        {"name": "file_name", "type": "Edm.String", "searchable": True, "filterable": True},
        {"name": "document_type", "type": "Edm.String", "searchable": False, "filterable": True, "facetable": True},
        {"name": "content", "type": "Edm.String", "searchable": True},
        {
            "name": "content_vector",
            "type": "Collection(Edm.Single)",
            "searchable": True,
            "dimensions": 1536,
            "vectorSearchProfile": "default-profile"
        },
        {"name": "extracted_data", "type": "Edm.String", "searchable": True},
        {"name": "processed_at", "type": "Edm.DateTimeOffset", "searchable": False, "filterable": True, "sortable": True},
    ],
    "vectorSearch": {
        "profiles": [
            {
                "name": "default-profile",
                "algorithm": "default-algorithm"
            }
        ],
        "algorithms": [
            {
                "name": "default-algorithm",
                "kind": "hnsw",
                "hnswParameters": {
                    "m": 4,
                    "efConstruction": 400,
                    "efSearch": 500,
                    "metric": "cosine"
                }
            }
        ]
    }
}


# Reusable HTTP client for Azure APIs
_http_client: Optional[httpx.Client] = None


def get_http_client() -> httpx.Client:
    """Get or create reusable HTTP client."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.Client(timeout=60)
    return _http_client


@traceable(name="index_document", run_type="chain")
def index_document(state: DocumentState) -> DocumentState:
    """Index processed document to Azure AI Search.

    Args:
        state: Document state with OCR and extracted data

    Returns:
        Updated state with indexing status
    """
    state.update_status(ProcessingStatus.INDEXING)

    # Skip if no OCR text
    if not state.ocr or not state.ocr.text:
        state.update_status(ProcessingStatus.INDEXED)
        return state

    try:
        # Ensure index exists
        ensure_index_exists()

        # Generate document ID from file name
        doc_id = hashlib.md5(state.file_name.encode()).hexdigest()

        # Limit content size once (used for both storage and embedding)
        content = state.ocr.text[:MAX_CONTENT_LENGTH]

        # Get embeddings for content
        embedding = get_embedding(content)

        # Prepare document for indexing
        doc = {
            "id": doc_id,
            "file_name": state.file_name,
            "document_type": state.document_type.value if state.document_type else "unknown",
            "content": content,
            "content_vector": embedding,
            "extracted_data": json.dumps(state.extracted.raw if state.extracted else {}, ensure_ascii=False),
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        # Upload to index
        upload_document(doc)

        state.update_status(ProcessingStatus.INDEXED)

    except httpx.HTTPStatusError as e:
        state.set_error(f"Indexing API error: {e.response.status_code} - {e.response.text[:200]}")

    except Exception as e:
        state.set_error(f"Indexing error: {str(e)}")

    return state


@traceable(name="ensure_index_exists", run_type="tool")
def ensure_index_exists() -> None:
    """Create index if it doesn't exist."""
    endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
    api_key = os.environ["AZURE_SEARCH_API_KEY"]
    index_name = os.environ.get("AZURE_SEARCH_INDEX", "processed-documents")

    url = f"{endpoint}/indexes/{index_name}?api-version=2024-07-01"
    headers = {
        "Content-Type": "application/json",
        "api-key": api_key,
    }

    client = get_http_client()

    # Check if index exists
    response = client.get(url, headers=headers)

    if response.status_code == 404:
        # Create index
        schema = INDEX_SCHEMA.copy()
        schema["name"] = index_name

        create_url = f"{endpoint}/indexes?api-version=2024-07-01"
        response = client.post(create_url, headers=headers, json=schema)

        if response.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"Failed to create index: {response.text}",
                request=response.request,
                response=response
            )

        print(f"Created index: {index_name}")


@traceable(name="get_embedding", run_type="embedding")
def get_embedding(text: str) -> list[float]:
    """Get embedding vector from Azure OpenAI.

    Args:
        text: Text to embed (should already be truncated)

    Returns:
        Embedding vector (1536 dimensions for text-embedding-3-small)
    """
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    api_key = os.environ["AZURE_OPENAI_KEY"]
    deployment = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")

    url = f"{endpoint}/openai/deployments/{deployment}/embeddings?api-version=2024-02-01"
    headers = {
        "Content-Type": "application/json",
        "api-key": api_key,
    }

    body = {
        "input": text,
    }

    client = get_http_client()
    response = client.post(url, headers=headers, json=body)
    response.raise_for_status()
    data = response.json()

    return data["data"][0]["embedding"]


@traceable(name="upload_document", run_type="tool")
def upload_document(doc: dict) -> None:
    """Upload document to Azure AI Search index.

    Args:
        doc: Document to upload
    """
    endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
    api_key = os.environ["AZURE_SEARCH_API_KEY"]
    index_name = os.environ.get("AZURE_SEARCH_INDEX", "processed-documents")

    url = f"{endpoint}/indexes/{index_name}/docs/index?api-version=2024-07-01"
    headers = {
        "Content-Type": "application/json",
        "api-key": api_key,
    }

    body = {
        "value": [
            {
                "@search.action": "mergeOrUpload",
                **doc
            }
        ]
    }

    client = get_http_client()
    response = client.post(url, headers=headers, json=body)
    response.raise_for_status()
