"""OCR node: Azure Document Intelligence (markdown output) + PyMuPDF (image extraction)."""

import hashlib
import os
from typing import Any

import fitz  # PyMuPDF
import httpx
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, AnalyzeResult, DocumentAnalysisFeature, DocumentContentFormat
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


_PLUMBER_KEY_HEADERS = {
    "街名", "物業簡稱", "建築面積", "每月租金", "地域", "地區",
    # common variants with line breaks collapsed
    "建築面積(尺)", "建築面積 (尺)", "每月租金(港元)",
}


def _extract_tables_pdfplumber(pdf_bytes: bytes) -> str:
    """Extract tables from a digital PDF using pdfplumber.

    Only keeps columns relevant for property extraction (building name, floor/unit,
    size, rent, district) — strips noise columns (管理費, 差餉, 間格, 備註, etc.)
    so the LLM receives a focused 5-6 column table rather than a 20+ column one.

    Applies fill-down for None/empty cells and normalises all whitespace to single
    spaces so every row stays on one line in the markdown output.

    Returns "" if pdfplumber finds no tables or the PDF has no text layer (scanned).
    """
    try:
        import io
        import pdfplumber

        parts: list[str] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            table_num = 0
            for page in pdf.pages:
                for table in page.extract_tables():
                    if not table or len(table) < 2:
                        continue
                    table_num += 1
                    col_count = max(len(row) for row in table)

                    # Normalise all cells: collapse whitespace, pad to col_count
                    def _norm(val: object) -> str:
                        return " ".join((val or "").split())

                    raw_rows = [
                        [_norm(c) for c in (list(row) + [""] * (col_count - len(row)))]
                        for row in table
                    ]

                    # Identify which columns to keep from the header row
                    header = raw_rows[0]
                    keep: list[int] = []
                    for idx, h in enumerate(header):
                        h_clean = h.replace(" ", "").replace("(", "").replace(")", "")
                        if any(
                            kw.replace(" ", "").replace("(", "").replace(")", "") in h_clean
                            or h_clean in kw.replace(" ", "").replace("(", "").replace(")", "")
                            for kw in _PLUMBER_KEY_HEADERS
                        ):
                            keep.append(idx)
                    # Always keep first col (listing ref) for context
                    if 0 not in keep:
                        keep = [0] + keep
                    if not keep:
                        keep = list(range(col_count))

                    # Apply fill-down on kept columns only
                    last_vals: list[str] = [""] * col_count
                    filled_rows: list[list[str]] = []
                    for row_idx, row in enumerate(raw_rows):
                        filled: list[str] = []
                        for col_idx in keep:
                            val = row[col_idx] if col_idx < len(row) else ""
                            if val:
                                last_vals[col_idx] = val
                                filled.append(val)
                            elif row_idx > 0:
                                filled.append(last_vals[col_idx])
                            else:
                                filled.append("")
                        filled_rows.append(filled)

                    n = len(keep)
                    lines = [
                        "| " + " | ".join(filled_rows[0]) + " |",
                        "| " + " | ".join(["---"] * n) + " |",
                    ]
                    for row in filled_rows[1:]:
                        lines.append("| " + " | ".join(row) + " |")
                    parts.append(f"TABLE {table_num}:\n" + "\n".join(lines))

        return "\n\n".join(parts)
    except Exception:
        return ""


_PDF_IMAGE_EXTS = {"pdf", "jpg", "jpeg", "png"}


def _di_features(ext: str) -> list:
    """Return DI features supported for this file type. KEY_VALUE_PAIRS is PDF/image only."""
    if ext in _PDF_IMAGE_EXTS:
        return [DocumentAnalysisFeature.KEY_VALUE_PAIRS]
    return []


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
    """Run OCR on a document. Uses file_bytes if available (dashboard path), otherwise downloads from blob_url (OneDrive path).
    If state.ocr is already populated (pre-computed from triage), skips DI entirely."""
    state.update_status(ProcessingStatus.OCR_PROCESSING)

    # Pre-computed OCR injected by the process endpoint — skip DI
    if state.ocr is not None and state.ocr.text:
        state.update_status(ProcessingStatus.OCR_COMPLETE)
        return state

    if state.file_bytes is not None:
        state.ocr = ocr_from_bytes(state.file_bytes, state.file_name)
        # file_bytes intentionally kept — odoo_sync (last node) uploads them to
        # Odoo Documents, then clears them.
    elif state.blob_url:
        state.ocr = ocr_from_url(state.blob_url, state.file_name)
    else:
        return state.set_error("No file bytes or blob URL provided for OCR")

    state.update_status(ProcessingStatus.OCR_COMPLETE)
    return state


@traceable(name="ocr_from_bytes")
def ocr_from_bytes(content: bytes, file_name: str = "") -> OCRResult:
    """Run OCR on raw document bytes (no URL needed — for direct file uploads).

    Args:
        content: Raw file bytes
        file_name: Original filename (used for image extraction)

    Returns:
        OCRResult with extracted text, tables, figures, and image URLs
    """
    from src.utils.di_guard import check_di_budget, record_di_usage

    check_di_budget()  # raises DailyLimitExceeded past the daily page ceiling

    config = get_config()
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""

    client = DocumentIntelligenceClient(
        endpoint=config.doc_intel.endpoint,
        credential=AzureKeyCredential(config.doc_intel.key),
    )
    poller = client.begin_analyze_document(
        model_id="prebuilt-layout",
        body=AnalyzeDocumentRequest(bytes_source=content),
        features=_di_features(ext),
        output_content_format=DocumentContentFormat.MARKDOWN,
    )
    result = poller.result()

    tables = _extract_tables(result)
    figures = _extract_figures(result)
    page_count = len(result.pages) if result.pages else 0
    record_di_usage(page_count)
    full_text = result.content if result.content else ""

    # Extract images and pdfplumber tables from PDF
    image_urls = []
    pdfplumber_markdown = ""
    if ext == "pdf":
        images = _extract_images_from_pdf(content, max_images=10)
        if images:
            doc_id = hashlib.md5(file_name.encode()).hexdigest()
            image_urls = upload_images_batch(images, doc_id)
        pdfplumber_markdown = _extract_tables_pdfplumber(content)

    return OCRResult(
        text=full_text,
        tables=tables,
        figures=figures,
        pages=page_count,
        confidence=0.97,
        image_urls=image_urls,
        pdfplumber_markdown=pdfplumber_markdown,
    )


@traceable(name="ocr_from_url")
def ocr_from_url(blob_url: str, file_name: str = "") -> OCRResult:
    """Run OCR on a document from URL.

    Args:
        blob_url: URL of the document to analyze
        file_name: Original filename (for image extraction)

    Returns:
        OCRResult with extracted text, tables, figures, and image URLs
    """
    from src.utils.di_guard import check_di_budget, record_di_usage

    check_di_budget()  # raises DailyLimitExceeded past the daily page ceiling

    config = get_config()

    client = DocumentIntelligenceClient(
        endpoint=config.doc_intel.endpoint,
        credential=AzureKeyCredential(config.doc_intel.key),
    )

    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""

    # Download PDF bytes upfront — needed for image extraction
    pdf_data: bytes | None = None
    if ext == "pdf":
        pdf_data = _download_document(blob_url)

    poller = client.begin_analyze_document(
        model_id="prebuilt-layout",
        body=AnalyzeDocumentRequest(url_source=blob_url),
        features=_di_features(ext),
        output_content_format=DocumentContentFormat.MARKDOWN,
    )
    result = poller.result()

    # Extract images and pdfplumber tables from PDF
    image_urls = []
    pdfplumber_markdown = ""
    if pdf_data:
        images = _extract_images_from_pdf(pdf_data, max_images=10)
        if images:
            doc_id = hashlib.md5(file_name.encode()).hexdigest()
            image_urls = upload_images_batch(images, doc_id)
        pdfplumber_markdown = _extract_tables_pdfplumber(pdf_data)

    page_count = len(result.pages) if result.pages else 0
    record_di_usage(page_count)

    return OCRResult(
        text=result.content if result.content else "",
        tables=_extract_tables(result),
        figures=_extract_figures(result),
        pages=page_count,
        confidence=0.97,
        image_urls=image_urls,
        pdfplumber_markdown=pdfplumber_markdown,
    )
