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


class ExtractionPath(str, Enum):
    """Extraction strategy chosen for this document.

    STRUCTURED   – standard single-pass LLM extraction (tables, forms, standard PDFs)
    CONVERSATIONAL – two-pass LangChain extraction for free-text / WhatsApp-style docs
                     with multiple properties, emoji separators, no tables
    VISUAL       – multimodal extraction for image-heavy pitching decks (future)
    """

    STRUCTURED = "structured"
    CONVERSATIONAL = "conversational"
    VISUAL = "visual"


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
    # Per-field confidence scores from the LLM (0.0–1.0).
    # Only populated by the conversational extractor.
    field_confidence: dict[str, float] = field(default_factory=dict)
    # Overall extraction confidence for this document.
    overall_confidence: float = 1.0


@dataclass
class DocumentState:
    """State object for document processing workflow.

    This state flows through all nodes in the LangGraph workflow.
    """

    # Input
    file_path: str = ""
    file_name: str = ""
    source: str = "onedrive"  # onedrive, dashboard, assistant, etc.
    whatsapp_number: str = ""  # sender's WhatsApp number (E.164), set for assistant/whatsapp jobs
    file_bytes: bytes | None = field(default=None, repr=False)  # set for direct uploads; cleared after OCR

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

    # Extraction path chosen by the analyzer
    extraction_path: ExtractionPath = ExtractionPath.STRUCTURED

    # Extraction
    extracted: ExtractedData = field(default_factory=ExtractedData)

    # Review flag — set by review_gate when confidence is low
    needs_review: bool = False

    # Indexing
    index_id: str = ""
    chunks_indexed: int = 0

    # Odoo sync (populated by odoo_sync / knowledge_sync nodes)
    odoo_record_id: str = ""
    odoo_sync_status: str = ""  # "synced", "pending", "skipped", "duplicate", "error"
    odoo_error_detail: str = "" # short error message when odoo_sync_status == "error"
    odoo_doc_url: str = ""      # Odoo Documents shareable URL for the source PDF
    skip_duplicate_check: bool = False  # user confirmed "process anyway" after a duplicate warning

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
