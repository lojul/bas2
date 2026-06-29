"""Structured extraction path — standard single-pass LLM extraction.

Used for: tables, standard forms, PDFs with clear field labels, single listings.
This is the original extractor, moved here so graph.py can route to it explicitly.
The public entry point is extract_structured(), which wraps the existing extractor.
"""

from langsmith import traceable

from src.state import DocumentState, ExtractionPath


@traceable(name="extract_structured", run_type="chain")
def extract_structured(state: DocumentState) -> DocumentState:
    """Run structured single-pass extraction (original pipeline).

    Delegates to the existing extractor.extract_data() which handles all
    DocumentType-specific prompts and table formatting.
    """
    from src.nodes.extractor import extract_data
    return extract_data(state)
