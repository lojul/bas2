"""Document state schema for the LangGraph workflow."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class DocumentType(str, Enum):
    """Classification of document types."""

    LISTING = "listing"
    LISTING_LIST = "listing_list"
    PITCHING_DECK = "pitching_deck"  # Property marketing/presentation deck
    NEWS = "news"
    CONTACT = "contact"
    UNKNOWN = "unknown"


class ProcessingStatus(str, Enum):
    """Status of document processing."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    UPLOADED = "uploaded"
    OCR_PROCESSING = "ocr_processing"
    OCR_COMPLETE = "ocr_complete"
    CLASSIFYING = "classifying"
    CLASSIFIED = "classified"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    INDEXING = "indexing"
    INDEXED = "indexed"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class OCRResult:
    """Results from Azure Document Intelligence OCR."""

    text: str = ""
    tables: list[dict[str, Any]] = field(default_factory=list)
    figures: list[dict[str, Any]] = field(default_factory=list)
    pages: int = 0
    confidence: float = 0.0
    image_urls: list[str] = field(default_factory=list)  # URLs of extracted images


@dataclass
class ExtractedData:
    """Structured data extracted from document."""

    raw: dict[str, Any] = field(default_factory=dict)
    document_type: DocumentType = DocumentType.UNKNOWN


@dataclass
class DocumentState:
    """State object for document processing workflow.

    This state flows through all nodes in the LangGraph workflow.
    """

    # Input
    file_path: str = ""
    file_name: str = ""
    source: str = "onedrive"  # onedrive, local, etc.

    # Processing state
    status: ProcessingStatus = ProcessingStatus.PENDING
    error_message: str = ""

    # Blob storage
    blob_url: str = ""

    # OCR results
    ocr: OCRResult = field(default_factory=OCRResult)

    # Classification
    document_type: DocumentType = DocumentType.UNKNOWN
    classification_confidence: float = 0.0

    # Analysis (pre-extraction structure analysis)
    analysis: dict[str, Any] = field(default_factory=dict)

    # Extraction
    extracted: ExtractedData = field(default_factory=ExtractedData)

    # Indexing
    index_id: str = ""
    chunks_indexed: int = 0

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    processing_time_ms: int = 0

    def update_status(self, status: ProcessingStatus) -> "DocumentState":
        """Update status and timestamp."""
        self.status = status
        self.updated_at = datetime.now()
        return self

    def set_error(self, message: str) -> "DocumentState":
        """Set error status with message."""
        self.status = ProcessingStatus.ERROR
        self.error_message = message
        self.updated_at = datetime.now()
        return self
