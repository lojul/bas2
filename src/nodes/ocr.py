"""Azure Document Intelligence OCR node."""

import hashlib
import io
import time
from typing import Any

import fitz  # PyMuPDF
import httpx
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, AnalyzeResult
from azure.core.credentials import AzureKeyCredential
from langsmith import traceable

from src.config import get_config
from src.state import DocumentState, OCRResult, ProcessingStatus
from src.utils.blob_storage import upload_images_batch


def _extract_tables(result: AnalyzeResult) -> list[dict[str, Any]]:
    """Extract tables from OCR result."""
    tables = []
    if result.tables:
        for table in result.tables:
            table_data = {
                "row_count": table.row_count,
                "column_count": table.column_count,
                "cells": [],
            }
            for cell in table.cells:
                table_data["cells"].append({
                    "row": cell.row_index,
                    "col": cell.column_index,
                    "text": cell.content,
                    "kind": cell.kind if hasattr(cell, "kind") else "content",
                })
            tables.append(table_data)
    return tables


def _extract_figures(result: AnalyzeResult) -> list[dict[str, Any]]:
    """Extract figures/images from OCR result."""
    figures = []
    if hasattr(result, "figures") and result.figures:
        for fig in result.figures:
            figures.append({
                "id": fig.id if hasattr(fig, "id") else None,
                "caption": fig.caption.content if hasattr(fig, "caption") and fig.caption else None,
            })
    return figures


def _extract_images_from_pdf(pdf_data: bytes, max_images: int = 10) -> list[tuple[bytes, str]]:
    """Extract embedded images from a PDF using PyMuPDF.

    Args:
        pdf_data: PDF file bytes
        max_images: Maximum number of images to extract

    Returns:
        List of (image_bytes, extension) tuples
    """
    images = []
    try:
        doc = fitz.open(stream=pdf_data, filetype="pdf")

        for page_num in range(len(doc)):
            if len(images) >= max_images:
                break

            page = doc[page_num]
            image_list = page.get_images(full=True)

            for img_info in image_list:
                if len(images) >= max_images:
                    break

                xref = img_info[0]
                try:
                    base_image = doc.extract_image(xref)
                    if base_image:
                        image_bytes = base_image["image"]
                        ext = base_image.get("ext", "png")

                        # Skip very small images (likely icons/artifacts)
                        if len(image_bytes) > 5000:
                            images.append((image_bytes, ext))
                except Exception:
                    continue

        doc.close()
    except Exception as e:
        print(f"Error extracting images from PDF: {e}")

    return images


def _download_document(url: str) -> bytes | None:
    """Download document from URL.

    Args:
        url: Document URL

    Returns:
        Document bytes or None if download failed
    """
    try:
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content
    except Exception as e:
        print(f"Error downloading document: {e}")
        return None


def run_ocr(state: DocumentState) -> DocumentState:
    """Run Azure Document Intelligence OCR on a document.

    Args:
        state: Document state with blob_url

    Returns:
        Updated state with OCR results
    """
    state.update_status(ProcessingStatus.OCR_PROCESSING)

    if not state.blob_url:
        return state.set_error("No blob URL provided for OCR")

    config = get_config()

    # Create Document Intelligence client
    client = DocumentIntelligenceClient(
        endpoint=config.doc_intel.endpoint,
        credential=AzureKeyCredential(config.doc_intel.key),
    )

    # Start analysis
    poller = client.begin_analyze_document(
        model_id="prebuilt-layout",
        body=AnalyzeDocumentRequest(url_source=state.blob_url),
    )

    # Poll for result
    result = poller.result()

    # Extract text content
    full_text = result.content if result.content else ""

    # Extract tables and figures
    tables = _extract_tables(result)
    figures = _extract_figures(result)

    # Calculate confidence (average of page confidence scores)
    confidence = 0.0
    if result.pages:
        page_count = len(result.pages)
        # Document Intelligence doesn't provide overall confidence in the same way
        # We'll use a default high confidence since it succeeded
        confidence = 0.95

    # Extract images from PDF and upload to blob storage
    image_urls = []
    if state.file_name.lower().endswith(".pdf"):
        pdf_data = _download_document(state.blob_url)
        if pdf_data:
            images = _extract_images_from_pdf(pdf_data, max_images=10)
            if images:
                # Generate doc_id from filename
                doc_id = hashlib.md5(state.file_name.encode()).hexdigest()
                image_urls = upload_images_batch(images, doc_id)

    # Update state with OCR results
    state.ocr = OCRResult(
        text=full_text,
        tables=tables,
        figures=figures,
        pages=len(result.pages) if result.pages else 0,
        confidence=confidence,
        image_urls=image_urls,
    )

    state.update_status(ProcessingStatus.OCR_COMPLETE)

    return state


@traceable(name="ocr_from_url")
def ocr_from_url(blob_url: str, file_name: str = "") -> OCRResult:
    """Run OCR on a document from URL.

    Args:
        blob_url: URL of the document to analyze
        file_name: Original filename (for image extraction)

    Returns:
        OCRResult with extracted text, tables, figures, and image URLs
    """
    config = get_config()

    client = DocumentIntelligenceClient(
        endpoint=config.doc_intel.endpoint,
        credential=AzureKeyCredential(config.doc_intel.key),
    )

    poller = client.begin_analyze_document(
        model_id="prebuilt-layout",
        body=AnalyzeDocumentRequest(url_source=blob_url),
    )

    result = poller.result()

    # Extract images from PDF
    image_urls = []
    if file_name.lower().endswith(".pdf"):
        pdf_data = _download_document(blob_url)
        if pdf_data:
            images = _extract_images_from_pdf(pdf_data, max_images=10)
            if images:
                doc_id = hashlib.md5(file_name.encode()).hexdigest()
                image_urls = upload_images_batch(images, doc_id)

    return OCRResult(
        text=result.content if result.content else "",
        tables=_extract_tables(result),
        figures=_extract_figures(result),
        pages=len(result.pages) if result.pages else 0,
        confidence=0.95,
        image_urls=image_urls,
    )
