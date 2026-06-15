"""Configuration management for Azure services and LangSmith."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class AzureDocIntelConfig:
    """Azure Document Intelligence configuration."""

    key: str
    endpoint: str


@dataclass(frozen=True)
class AzureBlobConfig:
    """Azure Blob Storage configuration."""

    account: str
    container: str
    read_sas: str
    images_container: str = "document-images"
    write_sas: str = ""

    @property
    def account_url(self) -> str:
        return f"https://{self.account}.blob.core.windows.net"

    @property
    def images_url(self) -> str:
        """URL for the images container."""
        return f"https://{self.account}.blob.core.windows.net/{self.images_container}"


@dataclass(frozen=True)
class AzureOpenAIConfig:
    """Azure OpenAI configuration."""

    endpoint: str
    key: str
    embedding_deployment: str = "text-embedding-3-small"


@dataclass(frozen=True)
class AzureSearchConfig:
    """Azure AI Search configuration."""

    endpoint: str
    index: str
    api_key: str


@dataclass(frozen=True)
class OpenRouterConfig:
    """OpenRouter configuration for LLM calls."""

    api_key: str
    base_url: str = "https://openrouter.ai/api/v1"


@dataclass(frozen=True)
class LangSmithConfig:
    """LangSmith observability configuration."""

    api_key: str
    project: str
    tracing_enabled: bool


@dataclass(frozen=True)
class MSGraphConfig:
    """Microsoft Graph API configuration for OneDrive."""

    client_id: str
    tenant_id: str
    client_secret: str

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}"

    @property
    def scope(self) -> list[str]:
        return ["https://graph.microsoft.com/.default"]


@dataclass(frozen=True)
class Config:
    """Main configuration container."""

    doc_intel: AzureDocIntelConfig
    blob: AzureBlobConfig
    openai: AzureOpenAIConfig
    search: AzureSearchConfig
    openrouter: OpenRouterConfig
    langsmith: LangSmithConfig
    msgraph: MSGraphConfig
    llama_cloud_api_key: str = ""


def load_config() -> Config:
    """Load configuration from environment variables."""
    return Config(
        doc_intel=AzureDocIntelConfig(
            key=os.environ["AZURE_DOC_INTEL_KEY"],
            endpoint=os.environ["AZURE_DOC_INTEL_ENDPOINT"],
        ),
        blob=AzureBlobConfig(
            account=os.environ["AZURE_BLOB_ACCOUNT"],
            container=os.environ["AZURE_BLOB_CONTAINER"],
            read_sas=os.environ["AZURE_BLOB_READ_SAS"],
            images_container=os.environ.get("AZURE_BLOB_IMAGES_CONTAINER", "document-images"),
            write_sas=os.environ.get("AZURE_BLOB_WRITE_SAS", ""),
        ),
        openai=AzureOpenAIConfig(
            endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            key=os.environ["AZURE_OPENAI_KEY"],
            embedding_deployment=os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small"),
        ),
        search=AzureSearchConfig(
            endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
            index=os.environ.get("AZURE_SEARCH_INDEX", "processed-documents"),
            api_key=os.environ["AZURE_SEARCH_API_KEY"],
        ),
        openrouter=OpenRouterConfig(
            api_key=os.environ["OPENROUTER_API_KEY"],
        ),
        langsmith=LangSmithConfig(
            api_key=os.environ["LANGCHAIN_API_KEY"],
            project=os.environ.get("LANGCHAIN_PROJECT", "document-processor"),
            tracing_enabled=os.environ.get("LANGCHAIN_TRACING_V2", "true").lower() == "true",
        ),
        msgraph=MSGraphConfig(
            client_id=os.environ["MS_GRAPH_CLIENT_ID"],
            tenant_id=os.environ["MS_GRAPH_TENANT_ID"],
            client_secret=os.environ["MS_GRAPH_CLIENT_SECRET"],
        ),
        llama_cloud_api_key=os.environ.get("LLAMA_CLOUD_API_KEY", ""),
    )


def get_config() -> Config:
    """Get configuration, loading from environment if needed."""
    return load_config()
