"""Shared Azure clients for tools that need them — managed identity only, no keys.

Same auth pattern as odoo-bas-sync and BAS's own ai-agent/clients.py:
DefaultAzureCredential everywhere. This service's identity needs:
  - Cognitive Services OpenAI User   on c21net-bas-oai-fc-ea-prod
  - Search Index Data Reader        on c21net-bas-srch-ea-prod (read-only —
    this service never writes to the index, unlike odoo-bas-sync)
"""

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from openai import AzureOpenAI

from core.config import (
    BAS_EMBEDDING_DEPLOYMENT,
    BAS_OPENAI_ENDPOINT,
    BAS_SEARCH_ENDPOINT,
    BAS_SEARCH_INDEX,
)

_credential = DefaultAzureCredential()

openai_client = AzureOpenAI(
    azure_endpoint=BAS_OPENAI_ENDPOINT,
    azure_ad_token_provider=get_bearer_token_provider(
        _credential, "https://cognitiveservices.azure.com/.default"
    ),
    api_version="2024-06-01",
)

search_client = SearchClient(
    endpoint=BAS_SEARCH_ENDPOINT,
    index_name=BAS_SEARCH_INDEX,
    credential=_credential,
)


def embed(text: str) -> list[float]:
    text = text[:8000]
    response = openai_client.embeddings.create(input=text, model=BAS_EMBEDDING_DEPLOYMENT)
    return response.data[0].embedding
