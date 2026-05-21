"""Main LangGraph workflow for document processing.

Workflow: get_download_url → run_ocr → classify
"""

import os
from typing import TypedDict

from langsmith import traceable
from langgraph.graph import END, START, StateGraph

from src.state import DocumentState, ProcessingStatus


class GraphState(TypedDict):
    """TypedDict wrapper for LangGraph state."""

    state: DocumentState


# =============================================================================
# Node functions (no @traceable - the underlying functions already have it)
# =============================================================================


def get_download_url_node(data: GraphState) -> GraphState:
    """Get download URL from OneDrive for the document."""
    from src.nodes.onedrive import get_download_url

    state = data["state"]
    state.update_status(ProcessingStatus.DOWNLOADING)

    try:
        drive_id = os.environ.get("MS_GRAPH_DRIVE_ID", "")
        item_id = state.file_path

        download_url = get_download_url(drive_id, item_id)

        if not download_url:
            return {"state": state.set_error(f"Could not get download URL for: {item_id}")}

        state.blob_url = download_url
        state.update_status(ProcessingStatus.UPLOADED)

    except Exception as e:
        state.set_error(f"OneDrive error: {str(e)}")

    return {"state": state}


def run_ocr_node(data: GraphState) -> GraphState:
    """Run OCR on document using Azure Document Intelligence."""
    from src.nodes.ocr import run_ocr

    state = data["state"]
    updated_state = run_ocr(state)
    return {"state": updated_state}


def classify_node(data: GraphState) -> GraphState:
    """Classify document type using AI."""
    from src.nodes.classifier import classify_document

    state = data["state"]
    updated_state = classify_document(state)
    return {"state": updated_state}


def extract_node(data: GraphState) -> GraphState:
    """Extract structured data based on document type."""
    from src.nodes.extractor import extract_data

    state = data["state"]
    updated_state = extract_data(state)
    return {"state": updated_state}


def index_node(data: GraphState) -> GraphState:
    """Index document to Azure AI Search."""
    from src.nodes.indexer import index_document

    state = data["state"]
    updated_state = index_document(state)
    return {"state": updated_state}


# =============================================================================
# Graph builder
# =============================================================================


def create_graph() -> StateGraph:
    """Create the document processing graph.

    start → get_download_url → run_ocr → classify → extract → index → end
    """
    graph = StateGraph(GraphState)

    # Add nodes
    graph.add_node("get_download_url", get_download_url_node)
    graph.add_node("run_ocr", run_ocr_node)
    graph.add_node("classify", classify_node)
    graph.add_node("extract", extract_node)
    graph.add_node("index", index_node)

    # Add edges
    graph.add_edge(START, "get_download_url")
    graph.add_edge("get_download_url", "run_ocr")
    graph.add_edge("run_ocr", "classify")
    graph.add_edge("classify", "extract")
    graph.add_edge("extract", "index")
    graph.add_edge("index", END)

    return graph


def compile_graph():
    """Compile the graph for execution."""
    return create_graph().compile()


# Compiled graph
app = compile_graph()


@traceable(name="process_file", run_type="chain")
def process_file(item_id: str, file_name: str) -> DocumentState:
    """Process a single document from OneDrive.

    Args:
        item_id: OneDrive item ID
        file_name: File name for display

    Returns:
        Final DocumentState after processing
    """
    initial_state = DocumentState(
        file_path=item_id,
        file_name=file_name,
        source="onedrive",
        status=ProcessingStatus.PENDING,
    )

    result = app.invoke({"state": initial_state})
    return result["state"]


def print_graph() -> None:
    """Print ASCII visualization of the graph."""
    compiled = create_graph().compile()
    print(compiled.get_graph().draw_ascii())


if __name__ == "__main__":
    print("Document Processor Graph:")
    print()
    print("  __start__ → get_download_url → run_ocr → classify → extract → index → __end__")
    print()
    print("Note: list_onedrive_files is handled by process_inbox.py")
