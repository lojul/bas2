"""Tests for configuration module."""

import os
from unittest.mock import patch

import pytest

from src.config import (
    AzureBlobConfig,
    AzureDocIntelConfig,
    AzureOpenAIConfig,
    AzureSearchConfig,
    Config,
    LangSmithConfig,
    OpenRouterConfig,
    load_config,
)


class TestAzureDocIntelConfig:
    """Tests for AzureDocIntelConfig."""

    def test_creation(self):
        """Should create config with key and endpoint."""
        config = AzureDocIntelConfig(
            key="test-key",
            endpoint="https://test.cognitiveservices.azure.com",
        )
        assert config.key == "test-key"
        assert config.endpoint == "https://test.cognitiveservices.azure.com"

    def test_immutable(self):
        """Config should be immutable (frozen dataclass)."""
        config = AzureDocIntelConfig(key="key", endpoint="endpoint")
        with pytest.raises(Exception):  # FrozenInstanceError
            config.key = "new-key"


class TestAzureBlobConfig:
    """Tests for AzureBlobConfig."""

    def test_creation(self):
        """Should create config with account, container, and SAS."""
        config = AzureBlobConfig(
            account="testaccount",
            container="testcontainer",
            read_sas="sas-token",
        )
        assert config.account == "testaccount"
        assert config.container == "testcontainer"
        assert config.read_sas == "sas-token"

    def test_account_url_property(self):
        """account_url should return correct blob URL."""
        config = AzureBlobConfig(
            account="myaccount",
            container="container",
            read_sas="sas",
        )
        assert config.account_url == "https://myaccount.blob.core.windows.net"


class TestAzureOpenAIConfig:
    """Tests for AzureOpenAIConfig."""

    def test_creation(self):
        """Should create config with endpoint and key."""
        config = AzureOpenAIConfig(
            endpoint="https://test.openai.azure.com",
            key="test-key",
        )
        assert config.endpoint == "https://test.openai.azure.com"
        assert config.key == "test-key"


class TestAzureSearchConfig:
    """Tests for AzureSearchConfig."""

    def test_creation(self):
        """Should create config with all search settings."""
        config = AzureSearchConfig(
            endpoint="https://test.search.windows.net",
            index="processed-documents",
            api_key="search-key",
        )
        assert config.endpoint == "https://test.search.windows.net"
        assert config.index == "processed-documents"
        assert config.api_key == "search-key"


class TestOpenRouterConfig:
    """Tests for OpenRouterConfig."""

    def test_creation_with_defaults(self):
        """Should create config with default base_url."""
        config = OpenRouterConfig(api_key="test-key")
        assert config.api_key == "test-key"
        assert config.base_url == "https://openrouter.ai/api/v1"

    def test_custom_base_url(self):
        """Should allow custom base_url."""
        config = OpenRouterConfig(
            api_key="test-key",
            base_url="https://custom.api.com",
        )
        assert config.base_url == "https://custom.api.com"


class TestLangSmithConfig:
    """Tests for LangSmithConfig."""

    def test_creation(self):
        """Should create config with all settings."""
        config = LangSmithConfig(
            api_key="ls-key",
            project="test-project",
            tracing_enabled=True,
        )
        assert config.api_key == "ls-key"
        assert config.project == "test-project"
        assert config.tracing_enabled is True


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_from_env(self):
        """Should load config from environment variables."""
        env_vars = {
            "AZURE_DOC_INTEL_KEY": "doc-key",
            "AZURE_DOC_INTEL_ENDPOINT": "https://doc.azure.com",
            "AZURE_BLOB_ACCOUNT": "blobaccount",
            "AZURE_BLOB_CONTAINER": "container",
            "AZURE_BLOB_READ_SAS": "sas-token",
            "AZURE_OPENAI_ENDPOINT": "https://openai.azure.com",
            "AZURE_OPENAI_KEY": "openai-key",
            "AZURE_SEARCH_ENDPOINT": "https://search.azure.com",
            "AZURE_SEARCH_INDEX": "processed-documents",
            "AZURE_SEARCH_API_KEY": "search-key",
            "OPENROUTER_API_KEY": "or-key",
            "LANGCHAIN_API_KEY": "lc-key",
            "LANGCHAIN_PROJECT": "test-project",
            "LANGCHAIN_TRACING_V2": "true",
            "MS_GRAPH_CLIENT_ID": "client-id",
            "MS_GRAPH_TENANT_ID": "tenant-id",
            "MS_GRAPH_CLIENT_SECRET": "client-secret",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            config = load_config()

        assert isinstance(config, Config)
        assert config.doc_intel.key == "doc-key"
        assert config.blob.account == "blobaccount"
        assert config.openai.endpoint == "https://openai.azure.com"
        assert config.search.index == "processed-documents"
        assert config.openrouter.api_key == "or-key"
        assert config.langsmith.project == "test-project"
        assert config.langsmith.tracing_enabled is True
        assert config.msgraph.client_id == "client-id"

    def test_load_config_missing_required_raises(self):
        """Should raise KeyError for missing required env vars."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(KeyError):
                load_config()

    def test_langsmith_tracing_defaults(self):
        """Should handle LANGCHAIN_TRACING_V2 default value."""
        env_vars = {
            "AZURE_DOC_INTEL_KEY": "key",
            "AZURE_DOC_INTEL_ENDPOINT": "endpoint",
            "AZURE_BLOB_ACCOUNT": "account",
            "AZURE_BLOB_CONTAINER": "container",
            "AZURE_BLOB_READ_SAS": "sas",
            "AZURE_OPENAI_ENDPOINT": "endpoint",
            "AZURE_OPENAI_KEY": "key",
            "AZURE_SEARCH_ENDPOINT": "endpoint",
            "AZURE_SEARCH_INDEX": "index",
            "AZURE_SEARCH_API_KEY": "key",
            "OPENROUTER_API_KEY": "key",
            "LANGCHAIN_API_KEY": "key",
            "MS_GRAPH_CLIENT_ID": "client-id",
            "MS_GRAPH_TENANT_ID": "tenant-id",
            "MS_GRAPH_CLIENT_SECRET": "client-secret",
            # LANGCHAIN_PROJECT and LANGCHAIN_TRACING_V2 not set
        }

        with patch.dict(os.environ, env_vars, clear=True):
            config = load_config()

        assert config.langsmith.project == "document-processor"
        assert config.langsmith.tracing_enabled is True
