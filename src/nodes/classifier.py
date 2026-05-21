"""Document classifier using OpenRouter AI."""

import os
import re
import httpx
from langsmith import traceable

from src.state import DocumentState, DocumentType, ProcessingStatus
from src.utils.json_parser import parse_json_response


CLASSIFY_PROMPT = """You are a Hong Kong property document classifier. Analyze the text and classify it.

File Info:
- Page Count: {page_count}
- Text Length: {text_length} characters
- Table Count: {table_count}

Classify as ONE of:

1. **listing_list** - Multi-property listing document (CHECK THIS FIRST):
   - Contains MULTIPLE numbered property entries (1), 2), 3)... or 1. 2. 3...)
   - Table format with repeated rows for DIFFERENT properties
   - Multiple 樓盤編號 (property IDs) in the document
   - Keywords: 旺舖出租精選, 物業列表, 精選推介
   - Columns like 地址, 面積, 租金 for EACH property
   - More than 3 distinct properties listed

2. **listing** - Single property for rent/sale:
   - ONE specific property only (may have multiple floors/units in SAME building)
   - Has asking rent or sale price for ONE property
   - Agent contact info
   - Keywords: 招租, 出售, For Lease, For Sale, Subject to Contract
   - Leasing proposal, sales brochure, tenancy terms

3. **news** - Market news, transaction report, or media article:
   - Completed transaction (成交, 售出, transaction)
   - News source, newspaper section
   - Reporter/journalist byline
   - Historical prices, profit/loss analysis

4. **contact** - Business card or contact information:
   - Person's name prominently displayed
   - Job title, company name
   - Phone numbers, email address
   - Usually short text with minimal property details

IMPORTANT: If you see multiple properties in a table with different addresses and prices, classify as "listing_list", NOT "listing".

Return ONLY valid JSON:
{{"type": "listing", "confidence": 0.9, "reason": "brief explanation"}}

TEXT TO CLASSIFY:
---
{text}
---

JSON:"""


def auto_detect_listing_list(text: str, table_count: int) -> bool:
    """Check if document looks like a multi-property listing based on patterns.

    Args:
        text: OCR text
        table_count: Number of tables detected

    Returns:
        True if document appears to be a listing_list
    """
    text_lower = text.lower()

    # Count property indicators
    property_id_count = len(re.findall(r'樓盤編號', text))
    vacant_count = len(re.findall(r'vacant|已吉|現吉', text_lower))
    rent_amounts = len(re.findall(r'\d{2,3},\d{3}', text))  # Rent amounts like 25,000

    # Multiple property indicators suggest listing_list
    if property_id_count >= 3:
        return True
    if vacant_count >= 3:
        return True
    if table_count >= 2 and rent_amounts >= 5:
        return True

    return False


def auto_detect_contact(text: str, text_length: int, page_count: int) -> bool:
    """Check if document looks like a business card/contact.

    Args:
        text: OCR text
        text_length: Total text length
        page_count: Number of pages

    Returns:
        True if document appears to be a contact
    """
    if text_length > 500 or page_count > 1:
        return False

    text_lower = text.lower()
    has_email = '@' in text or 'email' in text_lower
    has_phone = bool(re.search(r'\+?\d{2,3}[\s-]?\d{4}[\s-]?\d{4}', text))

    return has_email and has_phone


@traceable(name="classify_document", run_type="chain")
def classify_document(state: DocumentState) -> DocumentState:
    """Classify a document based on its OCR text.

    Args:
        state: Document state with OCR results

    Returns:
        Updated state with document_type and classification_confidence
    """
    state.update_status(ProcessingStatus.CLASSIFYING)

    # Get OCR text and metadata
    text = state.ocr.text if state.ocr else ""
    page_count = state.ocr.pages if state.ocr else 1
    table_count = len(state.ocr.tables) if state.ocr and state.ocr.tables else 0

    if not text:
        state.document_type = DocumentType.UNKNOWN
        state.classification_confidence = 0.0
        state.update_status(ProcessingStatus.CLASSIFIED)
        return state

    # Use more text for classification (4000 chars from start, 2000 from end)
    text_start = text[:4000]
    text_end = text[-2000:] if len(text) > 4000 else ""
    text_sample = text_start + ("\n...\n" + text_end if text_end else "")

    try:
        result = call_openrouter(text_sample, page_count, len(text), table_count)

        # Parse result
        doc_type = result.get("type", "unknown").lower()
        confidence = float(result.get("confidence", 0.5))

        # Auto-detection overrides
        if doc_type == "listing" and auto_detect_listing_list(text, table_count):
            doc_type = "listing_list"
            confidence = 0.85

        if doc_type != "contact" and auto_detect_contact(text, len(text), page_count):
            doc_type = "contact"
            confidence = 0.85

        # Map to DocumentType enum
        type_map = {
            "listing": DocumentType.LISTING,
            "listing_list": DocumentType.LISTING_LIST,
            "news": DocumentType.NEWS,
            "contact": DocumentType.CONTACT,
        }

        state.document_type = type_map.get(doc_type, DocumentType.UNKNOWN)
        state.classification_confidence = confidence
        state.update_status(ProcessingStatus.CLASSIFIED)

    except ValueError as e:
        # JSON parsing error
        state.document_type = DocumentType.UNKNOWN
        state.classification_confidence = 0.0
        state.set_error(f"Classification parse error: {str(e)}")

    except httpx.HTTPStatusError as e:
        # API error
        state.document_type = DocumentType.UNKNOWN
        state.classification_confidence = 0.0
        state.set_error(f"Classification API error: {e.response.status_code}")

    except Exception as e:
        state.document_type = DocumentType.UNKNOWN
        state.classification_confidence = 0.0
        state.set_error(f"Classification error: {str(e)}")

    return state


@traceable(name="classifier_openrouter", run_type="llm")
def call_openrouter(text: str, page_count: int = 1, text_length: int = 0, table_count: int = 0) -> dict:
    """Call OpenRouter API for classification.

    Args:
        text: Document text to classify
        page_count: Number of pages in document
        text_length: Total text length
        table_count: Number of tables detected

    Returns:
        Classification result dict with type, confidence, reason
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    prompt = CLASSIFY_PROMPT.format(
        text=text,
        page_count=page_count,
        text_length=text_length,
        table_count=table_count
    )

    body = {
        "model": "deepseek/deepseek-chat",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 150,
        "temperature": 0.1,  # Low temperature for consistent classification
    }

    with httpx.Client(timeout=30) as client:
        response = client.post(url, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()

    # Extract and parse content
    content = data["choices"][0]["message"]["content"]
    return parse_json_response(content)
