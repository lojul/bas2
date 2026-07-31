"""Main LangGraph workflow for document processing.

v2 — Odoo ingest service. Single entry point: process_file_from_bytes().
Documents arrive from WhatsApp (via n8n). No OneDrive timer, no AI Search writes.

  __start__
      │
  run_ocr           (Azure Document Intelligence + PyMuPDF images)
      │
  classify          (Qwen 2.5 — document type)
      │
  analyze           (regex signals → picks extraction_path)
      │
  ┌───┴──────────────────────────┬──────────────────────┐
  │                              │                      │
  extract_structured        extract_conversational  extract_vision
      │                              │                      │
  └───────────────┬──────────────┴──────────────────────┘
                  │
            review_gate       (sets needs_review flag if confidence < 0.75)
                  │
        ┌─────────┼──────────────────┬──────────────┐
        │         │                  │              │
   odoo_sync  knowledge_sync  contact_sync      reject
   (listing/  (news →         (contact →       (unknown)
    listing_    knowledge.      res.partner)
    list/       article)
    pitching_deck
    → x_c21_building
      x_c21_listing
      x_c21_extra_field)
"""

import logging
import time
from typing import TypedDict, Literal

from langsmith import traceable
from langgraph.graph import END, START, StateGraph

from src.state import DocumentState, DocumentType, ExtractionPath, ProcessingStatus

logger = logging.getLogger(__name__)


class GraphState(TypedDict):
    """TypedDict wrapper for LangGraph state."""
    state: DocumentState


# =============================================================================
# Node functions
# =============================================================================

def run_ocr_node(data: GraphState) -> GraphState:
    from src.nodes.ocr import run_ocr
    return {"state": run_ocr(data["state"])}


def classify_node(data: GraphState) -> GraphState:
    state = data["state"]

    # URL enrichment: when OCR text is short and contains a URL, fetch the article
    # content via Tavily so the classifier and extractor see the actual body.
    if state.ocr and state.ocr.text and len(state.ocr.text.strip()) < 300:
        from src.utils.url_fetcher import enrich_with_url_content
        enriched = enrich_with_url_content(state.ocr.text)
        if enriched != state.ocr.text:
            state.ocr.text = enriched

    # Caller already knows the type — skip LLM call
    if state.document_type != DocumentType.UNKNOWN:
        state.update_status(ProcessingStatus.CLASSIFIED)
        return {"state": state}

    from src.nodes.classifier import classify_document
    return {"state": classify_document(state)}


def analyze_node(data: GraphState) -> GraphState:
    from src.nodes.analyzer import analyze_document
    return {"state": analyze_document(data["state"])}


def extract_structured_node(data: GraphState) -> GraphState:
    from src.nodes.extractors.structured import extract_structured
    return {"state": extract_structured(data["state"])}


def extract_conversational_node(data: GraphState) -> GraphState:
    from src.nodes.extractors.conversational import extract_conversational
    return {"state": extract_conversational(data["state"])}


def extract_vision_node(data: GraphState) -> GraphState:
    from src.nodes.extractors.vision import extract_vision
    return {"state": extract_vision(data["state"])}


def review_gate_node(data: GraphState) -> GraphState:
    """Set needs_review flag based on extraction confidence.

    Does not change routing — all documents proceed to sync.
    The flag surfaces low-confidence documents for human review in Odoo.
    """
    state = data["state"]

    if state.extraction_path == ExtractionPath.STRUCTURED:
        raw = state.extracted.raw if state.extracted else {}
        has_data = raw and not raw.get("_extraction_failed") and not raw.get("_no_data")
        state.needs_review = not has_data

    return {"state": state}


def odoo_sync_node(data: GraphState) -> GraphState:
    from src.nodes.odoo_sync import odoo_sync
    return {"state": odoo_sync(data["state"])}


def knowledge_sync_node(data: GraphState) -> GraphState:
    from src.nodes.knowledge_sync import knowledge_sync
    return {"state": knowledge_sync(data["state"])}


def contact_sync_node(data: GraphState) -> GraphState:
    from src.nodes.contact_sync import contact_sync
    return {"state": contact_sync(data["state"])}


def reject_node(data: GraphState) -> GraphState:
    """Handle unknown or unprocessable documents — log and notify sender."""
    state = data["state"]
    logger.info("reject_node: unrecognised document type for '%s'", state.file_name)
    state.odoo_sync_status = "rejected"
    if state.whatsapp_number:
        try:
            from src.utils.whatsapp_notify import send_whatsapp
            send_whatsapp(
                state.whatsapp_number,
                f"⚠️ 無法處理文件 '{state.file_name}'：未能辨識文件類型。\n"
                "請確認這是物業資料、市場新聞或名片，然後重新傳送。",
            )
        except Exception as e:
            logger.warning("reject_node: WhatsApp notify failed: %s", e)
    return {"state": state}


# =============================================================================
# Routing
# =============================================================================

def route_extraction(data: GraphState) -> Literal["extract_structured", "extract_conversational", "extract_vision"]:
    path = data["state"].extraction_path
    if path == ExtractionPath.CONVERSATIONAL:
        return "extract_conversational"
    if path == ExtractionPath.VISUAL:
        return "extract_vision"
    return "extract_structured"


def route_sync(data: GraphState) -> Literal["odoo_sync", "knowledge_sync", "contact_sync", "reject"]:
    """Route to the correct Odoo sync target by document type."""
    doc_type = data["state"].document_type
    if doc_type in (DocumentType.LISTING, DocumentType.LISTING_LIST, DocumentType.PITCHING_DECK):
        return "odoo_sync"
    if doc_type == DocumentType.NEWS:
        return "knowledge_sync"
    if doc_type == DocumentType.CONTACT:
        return "contact_sync"
    return "reject"


# =============================================================================
# Graph builder
# =============================================================================

def create_graph() -> StateGraph:
    graph = StateGraph(GraphState)

    # ── Nodes ─────────────────────────────────────────────────────────────────
    graph.add_node("run_ocr", run_ocr_node)
    graph.add_node("classify", classify_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("extract_structured", extract_structured_node)
    graph.add_node("extract_conversational", extract_conversational_node)
    graph.add_node("extract_vision", extract_vision_node)
    graph.add_node("review_gate", review_gate_node)
    graph.add_node("odoo_sync", odoo_sync_node)
    graph.add_node("knowledge_sync", knowledge_sync_node)
    graph.add_node("contact_sync", contact_sync_node)
    graph.add_node("reject", reject_node)

    # ── Edges ─────────────────────────────────────────────────────────────────
    graph.add_edge(START, "run_ocr")
    graph.add_edge("run_ocr", "classify")
    graph.add_edge("classify", "analyze")

    graph.add_conditional_edges(
        "analyze",
        route_extraction,
        {
            "extract_structured": "extract_structured",
            "extract_conversational": "extract_conversational",
            "extract_vision": "extract_vision",
        },
    )

    graph.add_edge("extract_structured", "review_gate")
    graph.add_edge("extract_conversational", "review_gate")
    graph.add_edge("extract_vision", "review_gate")

    graph.add_conditional_edges(
        "review_gate",
        route_sync,
        {
            "odoo_sync": "odoo_sync",
            "knowledge_sync": "knowledge_sync",
            "contact_sync": "contact_sync",
            "reject": "reject",
        },
    )

    graph.add_edge("odoo_sync", END)
    graph.add_edge("knowledge_sync", END)
    graph.add_edge("contact_sync", END)
    graph.add_edge("reject", END)

    return graph


def compile_graph():
    return create_graph().compile()


# Compiled graph (module-level singleton)
app = compile_graph()


# =============================================================================
# Public entry point
# =============================================================================

@traceable(name="process_file_from_bytes", run_type="chain")
def process_file_from_bytes(
    file_bytes: bytes,
    file_name: str,
    source: str = "whatsapp",
    precomputed_ocr=None,  # OCRResult | None
    forced_type: DocumentType | None = None,
    skip_duplicate_check: bool = False,
    whatsapp_number: str = "",
) -> DocumentState:
    """Process a document from raw bytes through the full pipeline.

    All channels (WhatsApp via n8n, future channels) use this single entry point.
    Pass precomputed_ocr to skip the Azure DI call when triage already ran OCR.
    Pass forced_type when the caller already knows the document type.
    """
    from src.utils.table_storage import log_run

    initial_state = DocumentState(
        file_path="",
        file_name=file_name,
        source=source,
        whatsapp_number=whatsapp_number,
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
