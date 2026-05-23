"""Document data extractor using OpenRouter AI."""

import os
import httpx
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree

from src.state import DocumentState, DocumentType, ProcessingStatus, ExtractedData
from src.utils.json_parser import parse_json_response


# Extraction prompts for each document type
PROMPTS = {
    DocumentType.LISTING: """Extract the MAIN property listing data from this document.

IMPORTANT RULES:
- ONLY extract data that is EXPLICITLY stated in the text
- If a field is NOT found in the text, use null (not empty string, not made-up data)
- DO NOT invent or hallucinate any information
- If this text does NOT contain property listing information, return {{"_no_data": true}}

TEXT:
{text}

Return a SINGLE JSON object (NOT an array):
{{
  "building_name": "name from text or null",
  "address": "full address from text or null",
  "district": "area/district from text or null",
  "property_type": "office/retail/residential/industrial or null",
  "size_sqft": number from text or null,
  "rent_monthly": number from text or null,
  "floor": "floor from text or null",
  "unit": "unit from text or null",
  "contact_name": "agent name from text or null",
  "contact_phone": "phone number from text or null"
}}

Return ONLY the JSON object, no array, no explanation:""",

    DocumentType.LISTING_LIST: """Extract property listing table data.

IMPORTANT RULES:
- ONLY extract data that is EXPLICITLY stated in the text
- If a field is NOT found in the text, use null (not empty string, not made-up data)
- DO NOT invent or hallucinate any information
- If this text does NOT contain property listing information, return {{"_no_data": true}}

TEXT:
{text}

Return JSON with building info and list of available units (max 10 units):
{{
  "building_name": "name from text or null",
  "address": "address from text or null",
  "district": "area from text or null",
  "contact_phone": "phone from text or null",
  "units": [
    {{"floor": "from text", "unit": "from text", "size": number, "rent": number}}
  ]
}}

JSON only, no explanation:""",

    DocumentType.NEWS: """Extract news article information from this text.

TEXT:
{text}

Return a JSON object:
{{
  "title": "article title",
  "title_zh": "Chinese title if available",
  "date": "publication date (YYYY-MM-DD format if possible)",
  "author": "author name",
  "source": "publication/website name",
  "summary": "2-3 sentence summary of the article",
  "topics": ["property", "market", "etc"],
  "mentioned_properties": ["list of property names mentioned"],
  "mentioned_companies": ["list of company names mentioned"]
}}

JSON:""",

    DocumentType.CONTACT: """Extract contact/business card information from this text.

TEXT:
{text}

Return a JSON object:
{{
  "name": "person's full name",
  "name_zh": "Chinese name if available",
  "title": "job title",
  "company": "company name",
  "company_zh": "Chinese company name if available",
  "phone": "phone number",
  "mobile": "mobile number",
  "email": "email address",
  "address": "office address",
  "website": "website URL"
}}

JSON:""",

    DocumentType.PITCHING_DECK: """Extract comprehensive property development/marketing information from this pitching deck.

IMPORTANT RULES:
- Extract ALL information that is EXPLICITLY stated in the text
- If a field is NOT found, use null
- DO NOT invent or hallucinate any information
- For arrays, include all items found (up to 10)

TEXT:
{text}

Return a JSON object with ALL available information:
{{
  "project_name": "project/building name",
  "project_name_zh": "Chinese name if available",
  "developer": "developer company name",
  "address": "full address",
  "district": "area/district (e.g., North Point, Central)",
  "property_type": "mixed-use/retail/office/residential",

  "project_summary": {{
    "total_gfa_sqft": number or null,
    "retail_area_sqft": number or null,
    "office_area_sqft": number or null,
    "residential_units": number or null,
    "theatre_seats": number or null,
    "floors_retail": number or null,
    "floors_office": number or null,
    "floors_residential": number or null
  }},

  "available_units": [
    {{"unit": "G07", "floor": "G/F", "size_sqft": number, "facing": "Java Road", "features": "next to entrance"}}
  ],

  "availability_date": "Q4 2026 or specific date",

  "location": {{
    "mtr_stations": ["Fortress Hill (5 min)", "North Point (9 min)"],
    "bus_routes": ["description"],
    "catchment_population": number or null,
    "nearby_residential_units": number or null,
    "nearby_office_sqft": number or null,
    "nearby_hotels_rooms": number or null
  }},

  "nearby_buildings": ["AIA Tower", "China Taiping Finance Centre"],
  "nearby_schools": ["school names"],
  "tourist_attractions": ["attraction names"],

  "key_features": ["Grade I Historic Building", "Heritage conservation", "1st K11 Mall in HK Island"],

  "design_team": {{
    "architect": "firm name",
    "interior_designer": "firm name",
    "landscape_designer": "firm name"
  }},

  "contact": {{
    "name": "agent name",
    "phone": "phone number",
    "company": "company name"
  }}
}}

JSON:""",
}


@traceable(name="extract_data", run_type="chain")
def extract_data(state: DocumentState) -> DocumentState:
    """Extract structured data based on document type.

    Args:
        state: Document state with OCR results and classification

    Returns:
        Updated state with extracted data
    """
    state.update_status(ProcessingStatus.EXTRACTING)

    # Get OCR text and tables
    text = state.ocr.text if state.ocr else ""
    tables = state.ocr.tables if state.ocr else []
    doc_type = state.document_type

    # Format tables as text for LLM (Document Intelligence extracts these)
    tables_text = ""
    if tables:
        for i, table in enumerate(tables, 1):
            tables_text += f"\n\n=== TABLE {i} ===\n"
            # Group cells by row
            rows = {}
            for cell in table.get("cells", []):
                row_idx = cell.get("row", 0)
                if row_idx not in rows:
                    rows[row_idx] = []
                rows[row_idx].append((cell.get("col", 0), cell.get("text", "")))
            # Format rows
            for row_idx in sorted(rows.keys()):
                row_cells = sorted(rows[row_idx], key=lambda x: x[0])
                row_text = " | ".join(cell[1] for cell in row_cells)
                tables_text += row_text + "\n"

    # Combine text and tables
    full_text = text + tables_text

    if not full_text or doc_type == DocumentType.UNKNOWN:
        state.extracted = ExtractedData(
            raw={},
            document_type=doc_type,
        )
        state.update_status(ProcessingStatus.EXTRACTED)
        return state

    # Get prompt for this document type
    prompt_template = PROMPTS.get(doc_type)
    if not prompt_template:
        state.extracted = ExtractedData(raw={}, document_type=doc_type)
        state.update_status(ProcessingStatus.EXTRACTED)
        return state

    try:
        # Use text + tables for extraction - 16000 chars to include table data
        # Tables from Document Intelligence are appended after main text
        text_sample = full_text[:16000]
        result = call_openrouter(prompt_template.format(text=text_sample))

        state.extracted = ExtractedData(
            raw=result,
            document_type=doc_type,
        )
        state.update_status(ProcessingStatus.EXTRACTED)

    except ValueError as e:
        # JSON parsing error - store error info but don't fail silently
        state.extracted = ExtractedData(
            raw={"_extraction_failed": True, "_error": str(e)},
            document_type=doc_type
        )
        state.set_error(f"Extraction parse error: {str(e)}")

    except httpx.HTTPStatusError as e:
        state.extracted = ExtractedData(raw={}, document_type=doc_type)
        state.set_error(f"Extraction API error: {e.response.status_code}")

    except Exception as e:
        state.extracted = ExtractedData(raw={}, document_type=doc_type)
        state.set_error(f"Extraction error: {str(e)}")

    return state


@traceable(name="extractor_openrouter", run_type="llm")
def call_openrouter(prompt: str) -> dict:
    """Call OpenRouter API for extraction.

    Args:
        prompt: Full prompt with text

    Returns:
        Extracted data dict
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    body = {
        "model": "qwen/qwen-2.5-72b-instruct",  # Alibaba model - works in HK, excellent JSON output
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 4000,  # Increased for large listing tables
        "temperature": 0,  # Zero temp for deterministic extraction
    }

    with httpx.Client(timeout=60) as client:  # Longer timeout for extraction
        response = client.post(url, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()

    # Report token usage to LangSmith
    usage = data.get("usage", {})
    run_tree = get_current_run_tree()
    if run_tree and usage:
        run_tree.extra = run_tree.extra or {}
        run_tree.extra["usage_metadata"] = {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }

    # Extract and parse content
    content = data["choices"][0]["message"]["content"]
    return parse_json_response(content)
