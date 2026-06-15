"""Tests for Azure Document Intelligence OCR node."""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.state import DocumentState, ProcessingStatus, OCRResult


class TestRunOCR:
    """Tests for run_ocr function."""

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
    @patch("src.nodes.ocr.DocumentIntelligenceClient")
    def test_run_ocr_success(self, mock_client_class):
        """Should extract text from document."""
        from src.nodes.ocr import run_ocr

        # Setup mock OCR result
        mock_result = MagicMock()
        mock_result.content = "This is extracted text from the document."
        mock_result.tables = []
        mock_result.pages = [MagicMock(), MagicMock()]  # 2 pages

        mock_poller = MagicMock()
        mock_poller.result.return_value = mock_result

        mock_client = MagicMock()
        mock_client.begin_analyze_document.return_value = mock_poller
        mock_client_class.return_value = mock_client

        state = DocumentState(
            file_path="/test/doc.pdf",
            file_name="doc.pdf",
            blob_url="https://storage.blob.core.windows.net/container/doc.pdf?sas",
        )

        result = run_ocr(state)

        assert result.status == ProcessingStatus.OCR_COMPLETE
        assert result.ocr.text == "This is extracted text from the document."
        assert result.ocr.pages == 2
        assert result.ocr.confidence == 0.95
        assert result.error_message == ""

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
    def test_run_ocr_no_blob_url(self):
        """Should return error if no blob URL provided."""
        from src.nodes.ocr import run_ocr

        state = DocumentState(
            file_path="/test/doc.pdf",
            file_name="doc.pdf",
            blob_url="",  # No URL
        )

        result = run_ocr(state)

        assert result.status == ProcessingStatus.ERROR
        assert "no blob url" in result.error_message.lower()

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
        "MS_GRAPH_CLIENT_ID": "test-client-id",
        "MS_GRAPH_TENANT_ID": "test-tenant-id",
        "MS_GRAPH_CLIENT_SECRET": "test-secret",
    })
    @patch("src.nodes.ocr.DocumentIntelligenceClient")
    def test_run_ocr_with_tables(self, mock_client_class):
        """Should extract tables from document."""
        from src.nodes.ocr import run_ocr

        # Setup mock table
        mock_cell = MagicMock()
        mock_cell.row_index = 0
        mock_cell.column_index = 0
        mock_cell.content = "Header"
        mock_cell.kind = "columnHeader"

        mock_table = MagicMock()
        mock_table.row_count = 2
        mock_table.column_count = 3
        mock_table.cells = [mock_cell]

        mock_result = MagicMock()
        mock_result.content = "Table content"
        mock_result.tables = [mock_table]
        mock_result.pages = [MagicMock()]

        mock_poller = MagicMock()
        mock_poller.result.return_value = mock_result

        mock_client = MagicMock()
        mock_client.begin_analyze_document.return_value = mock_poller
        mock_client_class.return_value = mock_client

        state = DocumentState(
            file_path="/test/doc.pdf",
            file_name="doc.pdf",
            blob_url="https://storage.blob.core.windows.net/container/doc.pdf?sas",
        )

        result = run_ocr(state)

        assert result.status == ProcessingStatus.OCR_COMPLETE
        assert len(result.ocr.tables) == 1
        assert result.ocr.tables[0]["row_count"] == 2
        assert result.ocr.tables[0]["column_count"] == 3


class TestOCRFromUrl:
    """Tests for ocr_from_url function."""

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
        "MS_GRAPH_CLIENT_ID": "test-client-id",
        "MS_GRAPH_TENANT_ID": "test-tenant-id",
        "MS_GRAPH_CLIENT_SECRET": "test-secret",
    })
    @patch("src.nodes.ocr.DocumentIntelligenceClient")
    def test_ocr_from_url_success(self, mock_client_class):
        """Should return OCRResult directly."""
        from src.nodes.ocr import ocr_from_url

        mock_result = MagicMock()
        mock_result.content = "Extracted text"
        mock_result.tables = []
        mock_result.pages = [MagicMock()]

        mock_poller = MagicMock()
        mock_poller.result.return_value = mock_result

        mock_client = MagicMock()
        mock_client.begin_analyze_document.return_value = mock_poller
        mock_client_class.return_value = mock_client

        result = ocr_from_url("https://example.com/doc.pdf")

        assert isinstance(result, OCRResult)
        assert result.text == "Extracted text"
        assert result.pages == 1
