"""Tests for document state schema."""

from datetime import datetime

from src.state import (
    DocumentState,
    DocumentType,
    ExtractedData,
    OCRResult,
    ProcessingStatus,
)


class TestDocumentType:
    """Tests for DocumentType enum."""

    def test_all_document_types_exist(self):
        """Verify all expected document types are defined."""
        assert DocumentType.LISTING == "listing"
        assert DocumentType.LISTING_LIST == "listing_list"
        assert DocumentType.NEWS == "news"
        assert DocumentType.CONTACT == "contact"
        assert DocumentType.UNKNOWN == "unknown"

    def test_document_type_is_string_enum(self):
        """DocumentType values should be usable as strings."""
        assert str(DocumentType.LISTING) == "DocumentType.LISTING"
        assert DocumentType.LISTING.value == "listing"


class TestProcessingStatus:
    """Tests for ProcessingStatus enum."""

    def test_all_statuses_exist(self):
        """Verify all expected statuses are defined."""
        expected = [
            "pending",
            "downloading",
            "uploaded",
            "ocr_processing",
            "ocr_complete",
            "classifying",
            "classified",
            "extracting",
            "extracted",
            "indexing",
            "indexed",
            "complete",
            "error",
        ]
        actual = [s.value for s in ProcessingStatus]
        assert actual == expected


class TestOCRResult:
    """Tests for OCRResult dataclass."""

    def test_default_values(self):
        """OCRResult should have sensible defaults."""
        ocr = OCRResult()
        assert ocr.text == ""
        assert ocr.tables == []
        assert ocr.figures == []
        assert ocr.pages == 0
        assert ocr.confidence == 0.0

    def test_custom_values(self):
        """OCRResult should accept custom values."""
        ocr = OCRResult(
            text="Sample text",
            tables=[{"rows": 3}],
            figures=[{"type": "chart"}],
            pages=5,
            confidence=0.95,
        )
        assert ocr.text == "Sample text"
        assert len(ocr.tables) == 1
        assert len(ocr.figures) == 1
        assert ocr.pages == 5
        assert ocr.confidence == 0.95


class TestExtractedData:
    """Tests for ExtractedData dataclass."""

    def test_default_values(self):
        """ExtractedData should have sensible defaults."""
        data = ExtractedData()
        assert data.raw == {}
        assert data.document_type == DocumentType.UNKNOWN

    def test_custom_values(self):
        """ExtractedData should accept custom values."""
        data = ExtractedData(
            raw={"title": "Property", "price": 1000000},
            document_type=DocumentType.LISTING,
        )
        assert data.raw["title"] == "Property"
        assert data.document_type == DocumentType.LISTING


class TestDocumentState:
    """Tests for DocumentState dataclass."""

    def test_default_values(self):
        """DocumentState should have sensible defaults."""
        state = DocumentState()
        assert state.file_path == ""
        assert state.file_name == ""
        assert state.source == "onedrive"
        assert state.status == ProcessingStatus.PENDING
        assert state.error_message == ""
        assert state.blob_url == ""
        assert isinstance(state.ocr, OCRResult)
        assert state.document_type == DocumentType.UNKNOWN
        assert state.classification_confidence == 0.0
        assert isinstance(state.extracted, ExtractedData)
        assert state.index_id == ""
        assert state.chunks_indexed == 0
        assert isinstance(state.created_at, datetime)
        assert isinstance(state.updated_at, datetime)

    def test_custom_values(self, sample_file_path, sample_file_name):
        """DocumentState should accept custom values."""
        state = DocumentState(
            file_path=sample_file_path,
            file_name=sample_file_name,
            source="local",
        )
        assert state.file_path == sample_file_path
        assert state.file_name == sample_file_name
        assert state.source == "local"

    def test_update_status(self):
        """update_status should change status and update timestamp."""
        state = DocumentState()
        original_updated = state.updated_at

        state.update_status(ProcessingStatus.OCR_PROCESSING)

        assert state.status == ProcessingStatus.OCR_PROCESSING
        assert state.updated_at >= original_updated

    def test_set_error(self):
        """set_error should set error status and message."""
        state = DocumentState()

        state.set_error("Something went wrong")

        assert state.status == ProcessingStatus.ERROR
        assert state.error_message == "Something went wrong"

    def test_update_status_returns_self(self):
        """update_status should return self for chaining."""
        state = DocumentState()
        result = state.update_status(ProcessingStatus.COMPLETE)
        assert result is state

    def test_set_error_returns_self(self):
        """set_error should return self for chaining."""
        state = DocumentState()
        result = state.set_error("Error")
        assert result is state
