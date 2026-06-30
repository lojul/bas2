"""Vision extraction path — multimodal LLM for image-heavy pitching decks.

Used for: PDFs where Azure Document Intelligence returns very little text
(< 300 words) and document_type is pitching_deck — meaning content is
embedded in images/graphics rather than searchable text.

Architecture:
  1. Render each PDF page to a base64 PNG at 120 DPI (via PyMuPDF)
  2. Send pages to Qwen3-VL-32B in batches of 4
  3. Two extraction passes:
       Overview  — first batch (project name, developer, address, GFA, specs)
       Leasing   — last batch  (units, floors, rent, contacts)
  4. Merge both passes into a single ExtractedData dict
  5. If PDF bytes unavailable, fall back to structured extractor
"""

import os
import io
import json
import base64
import logging
from typing import Any

import httpx
from langsmith import traceable

from src.state import DocumentState, ExtractedData, DocumentType, ExtractionPath, ProcessingStatus

logger = logging.getLogger(__name__)

VISION_MODEL = "qwen/qwen3-vl-32b-instruct"
BATCH_SIZE = 4
DPI = 120  # 120 DPI keeps image sizes ~200-400 KB per page


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

OVERVIEW_PROMPT = (
    "You are extracting key facts from a Hong Kong property pitching deck / pre-leasing brochure. "
    "Look at ALL the images carefully — text may appear in graphics, infographics, and tables.\n\n"
    "Extract the following and return ONLY valid JSON (no markdown, no commentary):\n"
    "{\n"
    '  "project_name": "string or null",\n'
    '  "developer": "string or null",\n'
    '  "address": "string or null",\n'
    '  "district": "Chinese district name or null",\n'
    '  "property_type": "office/retail/residential/industrial/mixed or null",\n'
    '  "total_gfa_sqft": integer or null,\n'
    '  "completion_date": "string or null",\n'
    '  "floors_above_grade": integer or null,\n'
    '  "floor_to_ceiling_height_m": number or null,\n'
    '  "power_supply_va_sqm": integer or null,\n'
    '  "green_certification": "string or null",\n'
    '  "mtr_stations": ["list of nearby MTR stations"],\n'
    '  "key_features": ["list of key selling points"],\n'
    '  "notes": "any other important info"\n'
    "}\n\n"
    "Return null for any field you cannot find. Do NOT guess. Return ONLY the JSON."
)

LEASING_PROMPT = (
    "You are extracting leasing and unit details from a Hong Kong property pitching deck. "
    "Look at ALL the images carefully — floor plans, stacking charts, unit tables.\n\n"
    "Extract the following and return ONLY valid JSON (no markdown, no commentary):\n"
    "{\n"
    '  "available_units": [\n'
    '    {\n'
    '      "floor": "string or null",\n'
    '      "unit": "string or null",\n'
    '      "size_sqft": integer or null,\n'
    '      "size_sqm": number or null,\n'
    '      "rent_monthly": integer HKD or null,\n'
    '      "sell_price": integer HKD or null,\n'
    '      "facing": "string or null",\n'
    '      "status": "available/leased/sold or null"\n'
    "    }\n"
    "  ],\n"
    '  "typical_floor_sqft": integer or null,\n'
    '  "rent_psf_range": "string e.g. HK$45-55/sqft or null",\n'
    '  "contact_name": "string or null",\n'
    '  "contact_phone": "string or null",\n'
    '  "contact_email": "string or null",\n'
    '  "contact_company": "string or null"\n'
    "}\n\n"
    "Return an empty array [] for available_units if no unit data found. "
    "Return null for missing fields. Return ONLY the JSON."
)


# ---------------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------------

def _get_pdf_bytes(state: DocumentState) -> bytes | None:
    """Return raw PDF bytes from state or download from blob_url."""
    if state.file_bytes:
        return state.file_bytes

    if state.blob_url:
        try:
            with httpx.Client(timeout=60) as client:
                resp = client.get(state.blob_url)
                resp.raise_for_status()
                return resp.content
        except Exception as e:
            logger.warning("Failed to download PDF for vision: %s", e)
            return None

    return None


def _render_pages(pdf_bytes: bytes) -> list[str]:
    """Render every PDF page to a base64-encoded PNG at DPI resolution."""
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    zoom = DPI / 72.0  # 72 is PyMuPDF's base DPI
    mat = fitz.Matrix(zoom, zoom)
    pages_b64: list[str] = []

    for page in doc:
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_bytes = pix.tobytes("png")
        pages_b64.append(base64.b64encode(img_bytes).decode())

    doc.close()
    return pages_b64


# ---------------------------------------------------------------------------
# Vision LLM call
# ---------------------------------------------------------------------------

def _call_vision(pages_b64: list[str], prompt: str) -> dict:
    """Send a batch of page images to Qwen3-VL and parse the JSON response."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not configured")

    content: list[dict] = []
    for b64 in pages_b64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"},
        })
    content.append({"type": "text", "text": prompt})

    body = {
        "model": VISION_MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 2000,
        "temperature": 0,
    }

    with httpx.Client(timeout=120) as client:
        resp = client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        resp.raise_for_status()

    raw_text = resp.json()["choices"][0]["message"]["content"]

    # Strip markdown fences if present
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.rsplit("```", 1)[0].strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Vision LLM returned non-JSON: %s", raw_text[:200])
        return {}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

@traceable(name="extract_vision", run_type="chain")
def extract_vision(state: DocumentState) -> DocumentState:
    """Multimodal extraction for image-heavy pitching decks.

    Renders the PDF to images and sends them to Qwen3-VL-32B in two passes:
    - Overview pass: project metadata from first BATCH_SIZE pages
    - Leasing pass:  unit/floor data from last BATCH_SIZE pages (if different)

    Falls back to the structured extractor when PDF bytes are unavailable.
    """
    state.update_status(ProcessingStatus.EXTRACTING)

    pdf_bytes = _get_pdf_bytes(state)
    if not pdf_bytes:
        logger.warning(
            "Vision extraction: no PDF bytes for '%s', falling back to structured",
            state.file_name,
        )
        from src.nodes.extractors.structured import extract_structured
        state.extraction_path = ExtractionPath.STRUCTURED
        return extract_structured(state)

    try:
        logger.info("Vision extraction: rendering pages for '%s'", state.file_name)
        all_pages = _render_pages(pdf_bytes)
        n = len(all_pages)
        logger.info("Vision extraction: %d pages rendered", n)

        # Overview pass — first batch
        overview_pages = all_pages[:BATCH_SIZE]
        overview = _call_vision(overview_pages, OVERVIEW_PROMPT)
        logger.info("Vision overview extracted %d fields", len(overview))

        # Leasing pass — last batch (skip if same pages as overview)
        leasing: dict[str, Any] = {}
        if n > BATCH_SIZE:
            leasing_pages = all_pages[max(0, n - BATCH_SIZE):]
            leasing = _call_vision(leasing_pages, LEASING_PROMPT)
            logger.info("Vision leasing extracted %d fields", len(leasing))

        # Merge: overview is the base; leasing fields fill gaps / add units
        merged = _merge(overview, leasing)
        merged["extraction_path"] = "vision"
        merged["page_count"] = n

        state.extracted = ExtractedData(
            raw=merged,
            document_type=state.document_type,
            overall_confidence=0.85,
        )
        state.needs_review = False
        state.update_status(ProcessingStatus.EXTRACTED)

        logger.info(
            "Vision extraction complete for '%s': %d units, %d top-level fields",
            state.file_name,
            len(merged.get("available_units") or []),
            len(merged),
        )

    except Exception as e:
        logger.error("Vision extraction error for '%s': %s", state.file_name, e)
        state.extracted = ExtractedData(
            raw={"_extraction_failed": True, "_error": str(e)},
            document_type=state.document_type,
        )
        state.set_error(f"Vision extraction error: {e}")

    return state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _merge(overview: dict, leasing: dict) -> dict:
    """Merge leasing data into overview, preferring non-null values."""
    result = dict(overview)
    for key, val in leasing.items():
        if val is None or val == [] or val == "":
            continue
        if key not in result or result[key] is None or result[key] == [] or result[key] == "":
            result[key] = val
        elif isinstance(val, list) and isinstance(result.get(key), list):
            # Combine lists (units from both passes)
            existing = result[key]
            result[key] = existing + [v for v in val if v not in existing]
    return result
