"""Tests for Azure Blob Storage node."""

import os
from unittest.mock import MagicMock, patch, mock_open

import pytest

from src.state import DocumentState, ProcessingStatus


class TestUploadToBlob:
    """Tests for upload_to_blob function."""

    @patch.dict(os.environ, {
        "AZURE_DOC_INTEL_KEY": "test-key",
        "AZURE_DOC_INTEL_ENDPOINT": "https://test.cognitiveservices.azure.com",
        "AZURE_BLOB_ACCOUNT": "testaccount",
        "AZURE_BLOB_CONTAINER": "testcontainer",
        "AZURE_BLOB_READ_SAS": "sv=2020-08-04&ss=b&srt=sco&sp=r",
        "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
        "AZURE_OPENAI_KEY": "test-key",
        "AZURE_SEARCH_ENDPOINT": "https://test.search.windows.net",
        "AZURE_SEARCH_LISTING_INDEX": "listings",
        "AZURE_SEARCH_NEWS_INDEX": "news",
        "AZURE_SEARCH_API_KEY": "test-key",
        "OPENROUTER_API_KEY": "test-key",
        "LANGCHAIN_API_KEY": "test-key",
    })
    @patch("src.nodes.blob.BlobServiceClient")
    @patch("os.path.exists")
    @patch("builtins.open", mock_open(read_data=b"PDF content"))
    def test_upload_to_blob_success(self, mock_exists, mock_blob_service):
        """Should upload file and return blob URL."""
        from src.nodes.blob import upload_to_blob

        mock_exists.return_value = True

        # Setup mock blob client
        mock_blob_client = MagicMock()
        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_blob_service.return_value.get_container_client.return_value = mock_container_client

        state = DocumentState(
            file_path="/test/document.pdf",
            file_name="document.pdf",
        )

        result = upload_to_blob(state)

        assert result.status == ProcessingStatus.UPLOADED
        assert "testaccount.blob.core.windows.net" in result.blob_url
        assert "testcontainer" in result.blob_url
        assert result.error_message == ""
        mock_blob_client.upload_blob.assert_called_once()

    @patch.dict(os.environ, {
        "AZURE_DOC_INTEL_KEY": "test-key",
        "AZURE_DOC_INTEL_ENDPOINT": "https://test.cognitiveservices.azure.com",
        "AZURE_BLOB_ACCOUNT": "testaccount",
        "AZURE_BLOB_CONTAINER": "testcontainer",
        "AZURE_BLOB_READ_SAS": "sas-token",
        "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
        "AZURE_OPENAI_KEY": "test-key",
        "AZURE_SEARCH_ENDPOINT": "https://test.search.windows.net",
        "AZURE_SEARCH_LISTING_INDEX": "listings",
        "AZURE_SEARCH_NEWS_INDEX": "news",
        "AZURE_SEARCH_API_KEY": "test-key",
        "OPENROUTER_API_KEY": "test-key",
        "LANGCHAIN_API_KEY": "test-key",
    })
    @patch("os.path.exists")
    def test_upload_to_blob_file_not_found(self, mock_exists):
        """Should return error if file doesn't exist."""
        from src.nodes.blob import upload_to_blob

        mock_exists.return_value = False

        state = DocumentState(
            file_path="/nonexistent/file.pdf",
            file_name="file.pdf",
        )

        result = upload_to_blob(state)

        assert result.status == ProcessingStatus.ERROR
        assert "not found" in result.error_message.lower()


class TestUploadBytesToBlob:
    """Tests for upload_bytes_to_blob function."""

    @patch.dict(os.environ, {
        "AZURE_DOC_INTEL_KEY": "test-key",
        "AZURE_DOC_INTEL_ENDPOINT": "https://test.cognitiveservices.azure.com",
        "AZURE_BLOB_ACCOUNT": "testaccount",
        "AZURE_BLOB_CONTAINER": "testcontainer",
        "AZURE_BLOB_READ_SAS": "sas-token",
        "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com",
        "AZURE_OPENAI_KEY": "test-key",
        "AZURE_SEARCH_ENDPOINT": "https://test.search.windows.net",
        "AZURE_SEARCH_LISTING_INDEX": "listings",
        "AZURE_SEARCH_NEWS_INDEX": "news",
        "AZURE_SEARCH_API_KEY": "test-key",
        "OPENROUTER_API_KEY": "test-key",
        "LANGCHAIN_API_KEY": "test-key",
    })
    @patch("src.nodes.blob.BlobServiceClient")
    def test_upload_bytes_success(self, mock_blob_service):
        """Should upload bytes and return blob URL."""
        from src.nodes.blob import upload_bytes_to_blob

        mock_blob_client = MagicMock()
        mock_container_client = MagicMock()
        mock_container_client.get_blob_client.return_value = mock_blob_client
        mock_blob_service.return_value.get_container_client.return_value = mock_container_client

        result = upload_bytes_to_blob(
            file_bytes=b"PDF content",
            file_name="test.pdf",
            content_type="application/pdf",
        )

        assert "testaccount.blob.core.windows.net" in result
        assert "testcontainer" in result
        mock_blob_client.upload_blob.assert_called_once()
