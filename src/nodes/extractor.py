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

TEXT:
{text}

Return a SINGLE JSON object (NOT an array):
{{
  "building_name": "name",
  "address": "full address",
  "district": "area/district",
  "property_type": "office/retail/residential/industrial",
  "size_sqft": 1200,
  "rent_monthly": 25000,
  "floor": "3/F",
  "unit": "01",
  "contact_name": "agent name",
  "contact_phone": "phone number"
}}

Return ONLY the JSON object, no array, no explanation:""",

    DocumentType.LISTING_LIST: """Extract property listing table data.

TEXT:
{text}

Return JSON with building info and list of available units (max 10 units):
{{
  "building_name": "name",
  "address": "address",
  "district": "area",
  "contact_phone": "phone",
  "units": [
    {{"floor": "3/F", "unit": "01", "size": 1200, "rent": 25000}}
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

    # Get OCR text
    text = state.ocr.text if state.ocr else ""
    doc_type = state.document_type

    if not text or doc_type == DocumentType.UNKNOWN:
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
        # Use more text for extraction than classification (up to 4000 chars)
        text_sample = text[:4000]
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
        "model": "deepseek/deepseek-chat",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 4000,  # Increased for large listing tables
        "temperature": 0.1,
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
