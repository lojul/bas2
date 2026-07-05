"""Main LangGraph workflow for document processing.

Extraction paths (chosen by analyzer, no user input required):

  __start__
      │
  get_download_url  (OneDrive → download URL)
      │
  run_ocr           (Azure Document Intelligence + LlamaParse + PyMuPDF images)
      │
  classify          (Qwen 2.5 — document type)
      │
  analyze           (regex signals → picks extraction_path, then LLM structure scan)
      │
  ┌───┴──────────────────────────┬──────────────────────┐
  │                              │                      │
  extract_structured        extract_conversational  extract_vision
  (single-pass LLM,         (single-pass LangChain  (Qwen3-VL-32B,
   tables + forms)           for free-text prose)    image-heavy PDFs)
  │                              │                      │
  └───────────────┬──────────────┴──────────────────────┘
                  │
            review_gate       (sets needs_review flag if confidence < 0.75)
                  │
               index          (Azure AI Search + embeddings + smart merge — ALL types)
                  │
        ┌─────────┼──────────────────┐
        │         │                  │
   odoo_sync  knowledge_sync      __end__
   (listing/  (news →            (contact/
    listing_    knowledge.article)  unknown)
    list/
    pitching_deck
    → x_c21_listing)
        │         │
     __end__   __end__

Adding a new extraction path:
  1. Add a value to ExtractionPath in state.py
  2. Create src/nodes/extractors/<path>.py with a @traceable entry point
  3. Add a node + edge below and update route_extraction()
"""

import os
import time
from typing import TypedDict, Literal

from langsmith import traceable
from langgraph.graph import END, START, StateGraph

from src.state import DocumentState, DocumentType, ExtractionPath, ProcessingStatus


class GraphState(TypedDict):
    """TypedDict wrapper for LangGraph state."""
    state: DocumentState


# =============================================================================
# Node functions
# =============================================================================

def get_download_url_node(data: GraphState) -> GraphState:
    state = data["state"]
    # Dashboard path: bytes already in state — skip OneDrive download
    if state.file_bytes is not None:
        state.update_status(ProcessingStatus.UPLOADED)
        return {"state": state}
    # OneDrive path: fetch download URL from item ID
    from src.nodes.onedrive import get_download_url
    state.update_status(ProcessingStatus.DOWNLOADING)
    try:
        drive_id = os.environ.get("MS_GRAPH_DRIVE_ID", "")
        download_url = get_download_url(drive_id, state.file_path)
        if not download_url:
            return {"state": state.set_error(f"Could not get download URL for: {state.file_path}")}
        state.blob_url = download_url
        state.update_status(ProcessingStatus.UPLOADED)
    except Exception as e:
        state.set_error(f"OneDrive error: {e}")
    return {"state": state}


def run_ocr_node(data: GraphState) -> GraphState:
    from src.nodes.ocr import run_ocr
    return {"state": run_ocr(data["state"])}


def classify_node(data: GraphState) -> GraphState:
    state = data["state"]
    # Caller already knows the type (e.g. WhatsApp forwarded news image) — skip the LLM call
    if state.document_type != DocumentType.UNKNOWN:
        state.update_status(ProcessingStatus.CLASSIFIED)
        return {"state": state}
    from src.nodes.classifier import classify_document
    return {"state": classify_document(state)}


def analyze_node(data: GraphState) -> GraphState:
    """Analyze document structure and set state.extraction_path."""
    from src.nodes.analyzer import analyze_document
    return {"state": analyze_document(data["state"])}


def extract_structured_node(data: GraphState) -> GraphState:
    """Standard single-pass extraction for tables, forms, standard PDFs."""
    from src.nodes.extractors.structured import extract_structured
    return {"state": extract_structured(data["state"])}


def extract_conversational_node(data: GraphState) -> GraphState:
    """Two-pass LangChain extraction for free-text multi-property documents."""
    from src.nodes.extractors.conversational import extract_conversational
    return {"state": extract_conversational(data["state"])}


def extract_vision_node(data: GraphState) -> GraphState:
    """Multimodal extraction for image-heavy pitching decks."""
    from src.nodes.extractors.vision import extract_vision
    return {"state": extract_vision(data["state"])}


def review_gate_node(data: GraphState) -> GraphState:
    """Set needs_review flag based on extraction confidence.

    Does not change routing — all documents proceed to indexing.
    The flag surfaces low-confidence documents in the dashboard review queue.
    """
    state = data["state"]

    # Conversational path already sets needs_review in the extractor.
    # For structured path, flag if there's no extracted data at all.
    if state.extraction_path == ExtractionPath.STRUCTURED:
        raw = state.extracted.raw if state.extracted else {}
        has_data = raw and not raw.get("_extraction_failed") and not raw.get("_no_data")
        state.needs_review = not has_data

    return {"state": state}


def index_node(data: GraphState) -> GraphState:
    from src.nodes.indexer import index_document
    return {"state": index_document(data["state"])}


def odoo_sync_node(data: GraphState) -> GraphState:
    from src.nodes.odoo_sync import odoo_sync
    return {"state": odoo_sync(data["state"])}


def knowledge_sync_node(data: GraphState) -> GraphState:
    from src.nodes.knowledge_sync import knowledge_sync
    return {"state": knowledge_sync(data["state"])}


# =============================================================================
# Routing
# =============================================================================

def route_extraction(data: GraphState) -> Literal["extract_structured", "extract_conversational", "extract_vision"]:
    """Choose extraction path based on what the analyzer detected."""
    path = data["state"].extraction_path
    if path == ExtractionPath.CONVERSATIONAL:
        return "extract_conversational"
    if path == ExtractionPath.VISUAL:
        return "extract_vision"
    return "extract_structured"


def route_sync(data: GraphState) -> Literal["odoo_sync", "knowledge_sync", "end"]:
    """Route to the Odoo sync target by document type after indexing."""
    doc_type = data["state"].document_type
    if doc_type == DocumentType.NEWS:
        return "knowledge_sync"
    if doc_type in (DocumentType.LISTING, DocumentType.LISTING_LIST, DocumentType.PITCHING_DECK):
        return "odoo_sync"
    return "end"


# =============================================================================
# Graph builder
# =============================================================================

def create_graph() -> StateGraph:
    """Build the document processing graph with path-based routing."""
    graph = StateGraph(GraphState)

    # ── Nodes ─────────────────────────────────────────────────────────────────
    graph.add_node("get_download_url", get_download_url_node)
    graph.add_node("run_ocr", run_ocr_node)
    graph.add_node("classify", classify_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("extract_structured", extract_structured_node)
    graph.add_node("extract_conversational", extract_conversational_node)
    graph.add_node("extract_vision", extract_vision_node)
    graph.add_node("review_gate", review_gate_node)
    graph.add_node("index", index_node)
    graph.add_node("odoo_sync", odoo_sync_node)
    graph.add_node("knowledge_sync", knowledge_sync_node)

    # ── Edges ─────────────────────────────────────────────────────────────────
    graph.add_edge(START, "get_download_url")
    graph.add_edge("get_download_url", "run_ocr")
    graph.add_edge("run_ocr", "classify")
    graph.add_edge("classify", "analyze")

    # Conditional: analyzer decides which extractor to use
    graph.add_conditional_edges(
        "analyze",
        route_extraction,
        {
            "extract_structured": "extract_structured",
            "extract_conversational": "extract_conversational",
            "extract_vision": "extract_vision",
        },
    )

    # All extractors converge at review_gate
    graph.add_edge("extract_structured", "review_gate")
    graph.add_edge("extract_conversational", "review_gate")
    graph.add_edge("extract_vision", "review_gate")

    graph.add_edge("review_gate", "index")

    # Conditional: sync target depends on document type
    graph.add_conditional_edges(
        "index",
        route_sync,
        {
            "odoo_sync": "odoo_sync",
            "knowledge_sync": "knowledge_sync",
            "end": END,
        },
    )

    graph.add_edge("odoo_sync", END)
    graph.add_edge("knowledge_sync", END)

    return graph


def compile_graph():
    return create_graph().compile()


# Compiled graph (module-level singleton)
app = compile_graph()


# =============================================================================
# Public entry point
# =============================================================================

@traceable(name="process_file", run_type="chain")
def process_file(item_id: str, file_name: str) -> DocumentState:
    """Process a single document from OneDrive through the full pipeline."""
    from src.utils.table_storage import log_run

    initial_state = DocumentState(
        file_path=item_id,
        file_name=file_name,
        source="onedrive",
        status=ProcessingStatus.PENDING,
    )

    start_ms = time.monotonic()
    result = app.invoke({"state": initial_state})
    duration_ms = int((time.monotonic() - start_ms) * 1000)

    final: DocumentState = result["state"]
    is_error = final.status == ProcessingStatus.ERROR

    extracted = {}
    if final.extracted:
        try:
            from dataclasses import asdict
            extracted = asdict(final.extracted)
        except Exception:
            extracted = {}

    log_run(
        file_name=final.file_name,
        document_type=final.document_type.value if final.document_type else "unknown",
        status="error" if is_error else "success",
        duration_ms=duration_ms,
        extracted_data=extracted,
        error_message=final.error_message if is_error else None,
        index_id=final.index_id,
    )

    return final


@traceable(name="process_file_from_bytes", run_type="chain")
def process_file_from_bytes(
    file_bytes: bytes,
    file_name: str,
    source: str = "dashboard",
    precomputed_ocr=None,  # OCRResult | None
    forced_type: DocumentType | None = None,
    skip_duplicate_check: bool = False,
) -> DocumentState:
    """Process a document from raw bytes through the full pipeline (dashboard / manual upload path).

    Pass precomputed_ocr (an OCRResult) to skip the Azure DI call when triage already ran OCR
    on the full file (non-PDFs, or single-page PDFs).
    Pass forced_type when the caller already knows the document type (skips classification).
    """
    from src.utils.table_storage import log_run

    initial_state = DocumentState(
        file_path="",
        file_name=file_name,
        source=source,
        status=ProcessingStatus.PENDING,
        file_bytes=file_bytes,
        ocr=precomputed_ocr,
        document_type=forced_type or DocumentType.UNKNOWN,
        skip_duplicate_check=skip_duplicate_check,
    )

    start_ms = time.monotonic()
    result = app.invoke({"state": initial_state})
    duration_ms = int((time.monotonic() - start_ms) * 1000)

    final: DocumentState = result["state"]
    is_error = final.status == ProcessingStatus.ERROR

    extracted = {}
    if final.extracted:
        try:
            from dataclasses import asdict
            extracted = asdict(final.extracted)
        except Exception:
            extracted = {}

    log_run(
        file_name=final.file_name,
        document_type=final.document_type.value if final.document_type else "unknown",
        status="error" if is_error else "success",
        duration_ms=duration_ms,
        extracted_data=extracted,
        error_message=final.error_message if is_error else None,
        index_id=final.index_id,
    )

    return final


def print_graph() -> None:
    compiled = create_graph().compile()
    print(compiled.get_graph().draw_ascii())


if __name__ == "__main__":
    print_graph()
