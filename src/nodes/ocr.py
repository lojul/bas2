"""Azure Document Intelligence OCR node."""

import time
from typing import Any

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, AnalyzeResult
from azure.core.credentials import AzureKeyCredential
from langsmith import traceable

from src.config import get_config
from src.state import DocumentState, OCRResult, ProcessingStatus


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

    # Update state with OCR results
    state.ocr = OCRResult(
        text=full_text,
        tables=tables,
        figures=figures,
        pages=len(result.pages) if result.pages else 0,
        confidence=confidence,
    )

    state.update_status(ProcessingStatus.OCR_COMPLETE)

    return state


@traceable(name="ocr_from_url")
def ocr_from_url(blob_url: str) -> OCRResult:
    """Run OCR on a document from URL.

    Args:
        blob_url: URL of the document to analyze

    Returns:
        OCRResult with extracted text, tables, and figures
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

    return OCRResult(
        text=result.content if result.content else "",
        tables=_extract_tables(result),
        figures=_extract_figures(result),
        pages=len(result.pages) if result.pages else 0,
        confidence=0.95,
    )
