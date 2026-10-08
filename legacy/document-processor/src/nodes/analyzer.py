"""Document structure analyzer - pre-analyze before extraction.

Examines document content to identify:
- Available sections and fields
- Document structure (headings, tables, lists)
- Key data points present
- Recommended extraction path (structured / conversational / visual)
"""

import os
import re
import httpx
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree

from src.state import DocumentState, DocumentType, ExtractionPath, ProcessingStatus
from src.utils.json_parser import parse_json_response


ANALYSIS_PROMPT = """Analyze this document and identify what information is available for extraction.

DOCUMENT TEXT:
{text}

DOCUMENT METADATA:
- Page Count: {page_count}
- Text Length: {text_length} characters
- Table Count: {table_count}

Analyze the document and return a JSON object describing:
1. What sections/topics are present
2. What specific data fields are found
3. What key information can be extracted

Return ONLY valid JSON:
{{
  "document_structure": {{
    "has_project_overview": true/false,
    "has_property_details": true/false,
    "has_demographic_data": true/false,
    "has_floor_plans": true/false,
    "has_pricing_info": true/false,
    "has_unit_listings": true/false,
    "has_contact_info": true/false,
    "has_location_info": true/false,
    "has_news_content": true/false
  }},

  "available_fields": [
    "building_name",
    "address",
    "district",
    "etc - list all fields found"
  ],

  "key_entities": {{
    "building_names": ["list of building/project names found"],
    "addresses": ["list of addresses found"],
    "companies": ["list of company names found"],
    "prices": ["list of price/rent amounts found"],
    "sizes": ["list of size measurements found"],
    "dates": ["list of dates found"]
  }},

  "sections_found": [
    "list section headings or topics identified"
  ],

  "extraction_notes": "Brief notes on what unique info this document contains"
}}

JSON:"""


@traceable(name="analyze_document", run_type="chain")
def analyze_document(state: DocumentState) -> DocumentState:
    """Pre-analyze document structure before extraction.

    Identifies available fields, sections, and key entities
    to guide adaptive extraction.

    Args:
        state: Document state with OCR results and classification

    Returns:
        Updated state with analysis metadata
    """
    # Get OCR text and metadata
    text = state.ocr.text if state.ocr else ""
    page_count = state.ocr.pages if state.ocr else 1
    table_count = len(state.ocr.tables) if state.ocr and state.ocr.tables else 0

    if not text:
        return state

    # Determine extraction path (fast, no LLM) — uses document_type as primary signal
    state.extraction_path = determine_extraction_path(
        text, state.file_name, table_count, page_count, state.document_type
    )

    try:
        # Sample text from different parts of document
        text_start = text[:6000]
        text_middle = text[len(text)//3:len(text)//3 + 2000] if len(text) > 6000 else ""
        text_end = text[-3000:] if len(text) > 6000 else ""
        text_sample = text_start + ("\n...\n" + text_middle if text_middle else "") + ("\n...\n" + text_end if text_end else "")

        # Call LLM for analysis
        analysis = call_analysis_llm(
            text_sample,
            page_count,
            len(text),
            table_count
        )

        # Store analysis in state metadata
        if not hasattr(state, 'analysis') or state.analysis is None:
            state.analysis = {}
        state.analysis = analysis

    except Exception as e:
        # Analysis is optional - don't fail pipeline
        state.analysis = {"error": str(e)}

    return state


@traceable(name="analyzer_openrouter", run_type="llm")
def call_analysis_llm(text: str, page_count: int, text_length: int, table_count: int) -> dict:
    """Call LLM to analyze document structure.

    Args:
        text: Document text sample
        page_count: Number of pages
        text_length: Total text length
        table_count: Number of tables

    Returns:
        Analysis dict with structure, fields, entities
    """
    prompt = ANALYSIS_PROMPT.format(
        text=text,
        page_count=page_count,
        text_length=text_length,
        table_count=table_count
    )

    from src.utils.llm import openrouter_chat
    data = openrouter_chat(prompt, max_tokens=2000, temperature=0.0)

    # Report token usage
    usage = data.get("usage", {})
    run_tree = get_current_run_tree()
    if run_tree and usage:
        run_tree.extra = run_tree.extra or {}
        run_tree.extra["usage_metadata"] = {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }

    content = data["choices"][0]["message"]["content"]
    return parse_json_response(content)


def determine_extraction_path(
    text: str,
    file_name: str,
    table_count: int,
    page_count: int,
    document_type=None,
) -> ExtractionPath:
    """Choose the best extraction path from document type + text signals.

    document_type is the PRIMARY signal (set by the classifier).
    Text signals are used only for listing / listing_list to decide
    whether the document is a table-structured form (STRUCTURED) or
    free-text prose with multiple entities (CONVERSATIONAL).

    Type → path mapping:
      pitching_deck  → STRUCTURED (always — multi-section but prompt handles it)
      news           → STRUCTURED (always — single article)
      contact        → STRUCTURED (always — single card)
      listing        → STRUCTURED (single property, even if free-text)
      listing_list   → STRUCTURED if has tables; CONVERSATIONAL if free-text prose
      unknown        → STRUCTURED (fallback)
    """
    from src.state import DocumentType

    # Image-heavy pitching decks: route to vision extractor when OCR text is sparse
    # (< 300 words means content is embedded in images, not searchable text)
    if document_type == DocumentType.PITCHING_DECK:
        word_count = len(text.split())
        if word_count < 800:
            return ExtractionPath.VISUAL
        return ExtractionPath.STRUCTURED

    # Types that never need conversational extraction
    if document_type in (DocumentType.NEWS, DocumentType.CONTACT,
                         DocumentType.LISTING, DocumentType.UNKNOWN):
        return ExtractionPath.STRUCTURED

    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""

    # listing_list: only go conversational when there are NO tables
    # (tables → structured extractor handles the row-by-row parsing perfectly)
    if document_type == DocumentType.LISTING_LIST and table_count == 0:
        # Additional signals that confirm it's genuinely free-text multi-property
        price_points = len(re.findall(r"\$[\d,]+(億|萬)", text))
        price_emoji = len(re.findall(r"💰|💵", text))
        address_hits = len(re.findall(
            r"\d+[A-Za-z]?\s*[-–]?\s*\d*[A-Za-z]?\s+"
            r"(?:Nathan Road|彌敦道|道|街|路|Avenue|Street|Road)",
            text,
        ))
        is_free_text = (
            ext == "docx"
            or price_emoji >= 2
            or price_points >= 2
            or address_hits >= 2
        )
        if is_free_text:
            return ExtractionPath.CONVERSATIONAL

    return ExtractionPath.STRUCTURED


def quick_structure_scan(text: str) -> dict:
    """Quick regex-based scan for document structure (no LLM call).

    Use this for fast initial assessment.

    Args:
        text: Document text

    Returns:
        Dict with detected patterns
    """
    text_lower = text.lower()

    return {
        "has_project_overview": any(kw in text_lower for kw in [
            'project summary', 're-development', 'transformation', 'overview'
        ]),
        "has_demographic_data": any(kw in text_lower for kw in [
            'demographic', 'population', 'catchment', 'income'
        ]),
        "has_floor_plans": any(kw in text_lower for kw in [
            'floor plan', 'stacking', 'layout', 'dimension'
        ]),
        "has_pricing_info": bool(re.search(r'(?:hk\$|租金|rent|price).*\d', text_lower)),
        "has_unit_listings": bool(re.search(r'(?:unit|shop|floor).*(?:sqft|sq\.?ft|呎)', text_lower)),
        "has_contact_info": '@' in text or bool(re.search(r'\d{4}[\s-]?\d{4}', text)),
        "has_location_info": any(kw in text_lower for kw in [
            'mtr', 'station', 'walking distance', 'location', '地鐵'
        ]),

        # Count patterns
        "price_count": len(re.findall(r'\$[\d,]+|\d+,\d{3}', text)),
        "sqft_count": len(re.findall(r'[\d,]+\s*(?:sqft|sq\.?ft|平方呎|呎)', text_lower)),
        "phone_count": len(re.findall(r'\d{4}[\s-]?\d{4}', text)),
    }
