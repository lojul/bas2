"""Embed + upsert into BAS's properties-index, via managed identity — no keys.

Same auth pattern as business-automation-system/ai-agent/src/clients.py: managed
identity (DefaultAzureCredential) for both Azure OpenAI and Azure AI Search. This
Function App's identity was granted:
  - Cognitive Services OpenAI User  on c21net-bas-oai-fc-ea-prod
  - Search Index Data Contributor  on c21net-bas-srch-ea-prod
"""

import logging
import os

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from openai import AzureOpenAI

BAS_OPENAI_ENDPOINT = os.environ.get(
    "BAS_OPENAI_ENDPOINT", "https://c21net-bas-oai-fc-ea-prod.openai.azure.com"
)
BAS_EMBEDDING_DEPLOYMENT = os.environ.get("BAS_EMBEDDING_DEPLOYMENT", "text-embedding-3-large")
BAS_SEARCH_ENDPOINT = os.environ.get(
    "BAS_SEARCH_ENDPOINT", "https://c21net-bas-srch-ea-prod.search.windows.net"
)
BAS_SEARCH_INDEX = os.environ.get("BAS_SEARCH_INDEX", "properties-index")

_credential = DefaultAzureCredential()

_openai_client = AzureOpenAI(
    azure_endpoint=BAS_OPENAI_ENDPOINT,
    azure_ad_token_provider=get_bearer_token_provider(
        _credential, "https://cognitiveservices.azure.com/.default"
    ),
    api_version="2024-06-01",
)

_search_client = SearchClient(
    endpoint=BAS_SEARCH_ENDPOINT,
    index_name=BAS_SEARCH_INDEX,
    credential=_credential,
)


def embed(text: str) -> list[float]:
    """Azure OpenAI embedding, same model/dims BAS's own index uses (3072-dim)."""
    text = text[:8000]  # keep well under the embedding model's input token limit
    response = _openai_client.embeddings.create(
        input=text,
        model=BAS_EMBEDDING_DEPLOYMENT,
    )
    return response.data[0].embedding


def upsert(doc: dict) -> None:
    """merge_or_upload — idempotent on doc['id'], matches etl-pipeline's own upsert shape."""
    result = _search_client.merge_or_upload_documents([doc])
    if not result[0].succeeded:
        raise RuntimeError(f"Search upsert failed for {doc['id']}: {result[0].error_message}")
    logging.info("bas_sync: upserted %s", doc["id"])
