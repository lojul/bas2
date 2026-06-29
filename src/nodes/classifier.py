"""Document classifier — Azure OpenAI (primary) with OpenRouter fallback."""

import os
import re
import httpx
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree

from src.state import DocumentState, DocumentType, ProcessingStatus
from src.utils.json_parser import parse_json_response


CLASSIFY_PROMPT = """You are a Hong Kong property document classifier. Analyze the text and classify it.

File Info:
- Page Count: {page_count}
- Text Length: {text_length} characters
- Table Count: {table_count}

Classify as ONE of:

1. **pitching_deck** - Property marketing/presentation deck (CHECK THIS FIRST for multi-page docs):
   - Professional presentation format (10+ pages)
   - Project overview with developer branding (K11, Henderson, Swire, etc.)
   - Contains demographics, catchment area, population data
   - Floor plans, stacking diagrams, traffic flow
   - Multiple sections: location, project summary, leasing proposal
   - Keywords: Pitching, Re-development, Project Summary, Demographic, Catchment, Heritage
   - Mixed-use developments with retail + office + residential components
   - High-quality renders, maps, transformation visuals

2. **listing_list** - Multi-unit listing document (rent OR sale):
   - Contains MULTIPLE units/floors in ONE building, OR multiple different properties
   - Table format with repeated rows: floor, unit, size, rent/price columns
   - Keywords (rent): 旺舖出租精選, 物業列表, 招租, 月租, 租金
   - Keywords (sale): 售價, 賣價, For Sale, sale price, price per sq.ft
   - Examples: floor-by-floor unit table, building availability schedule
   - More than 2 distinct units or floors listed in a table

3. **listing** - Single unit/property for rent or sale:
   - ONE specific unit only (single floor, single suite)
   - Has asking rent or sale price for ONE unit
   - Agent contact info
   - Keywords: 招租, 出售, For Lease, For Sale, Subject to Contract
   - Leasing proposal, sales brochure, tenancy terms (simple format)

4. **news** - Market news, transaction report, or media article:
   - Completed transaction (成交, 售出, transaction)
   - News source, newspaper section
   - Reporter/journalist byline
   - Historical prices, profit/loss analysis

5. **contact** - Business card or contact information:
   - Person's name prominently displayed
   - Job title, company name
   - Phone numbers, email address
   - Usually short text with minimal property details

IMPORTANT:
- If page_count >= 10 with demographics/project overview, classify as "pitching_deck"
- If you see multiple properties with different addresses, classify as "listing_list"

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
    # Sale prices in HK$ millions (e.g. 12,000,000 or 1,200,000)
    sale_prices = len(re.findall(r'\d{1,2},\d{3},\d{3}', text))
    sale_keywords = len(re.findall(r'售價|賣價|for sale|sale price|price per s', text_lower))

    # Multiple property indicators suggest listing_list
    if property_id_count >= 3:
        return True
    if vacant_count >= 3:
        return True
    if table_count >= 2 and rent_amounts >= 5:
        return True
    # Sale listing: table with multiple sale prices
    if table_count >= 1 and sale_prices >= 3:
        return True
    if table_count >= 1 and sale_keywords >= 2 and sale_prices >= 1:
        return True

    return False


def auto_detect_pitching_deck(text: str, text_length: int, page_count: int) -> bool:
    """Check if document looks like a pitching/marketing deck.

    Args:
        text: OCR text
        text_length: Total text length
        page_count: Number of pages

    Returns:
        True if document appears to be a pitching deck
    """
    # Must be multi-page document
    if page_count < 8:
        return False

    text_lower = text.lower()

    # Key indicators of pitching decks
    pitching_keywords = [
        'demographic', 'catchment', 'population', 'project summary',
        're-development', 'redevelopment', 'transformation', 'heritage',
        'stacking plan', 'stacking', 'traffic flow', 'floor plan',
        'leasing proposal', 'by k11', 'k11 mall', 'by henderson',
        'by swire', 'by new world', 'walking distance', 'residential units',
        'office area', 'retail area', 'pitching', 'dimension plan',
        '人口', '步行', '寫字樓', '零售', '住宅', '商場', '項目概覽'
    ]

    keyword_count = sum(1 for kw in pitching_keywords if kw in text_lower)

    # If 2+ pitching keywords found in a multi-page doc, it's likely a deck
    return keyword_count >= 2


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
        result = call_llm(text_sample, page_count, len(text), table_count)

        # Parse result
        doc_type = result.get("type", "unknown").lower()
        confidence = float(result.get("confidence", 0.5))

        # Auto-detection overrides
        # Check for pitching deck first (multi-page professional presentations)
        if doc_type in ("listing", "listing_list") and auto_detect_pitching_deck(text, len(text), page_count):
            doc_type = "pitching_deck"
            confidence = 0.90

        if doc_type == "listing" and auto_detect_listing_list(text, table_count):
            doc_type = "listing_list"
            confidence = 0.85

        if doc_type != "contact" and auto_detect_contact(text, len(text), page_count):
            doc_type = "contact"
            confidence = 0.85

        # Fallback: if LLM returns "unknown" but has tables, likely a listing_list
        if doc_type == "unknown" and table_count >= 1:
            doc_type = "listing_list"
            confidence = 0.60

        # Map to DocumentType enum
        type_map = {
            "listing": DocumentType.LISTING,
            "listing_list": DocumentType.LISTING_LIST,
            "pitching_deck": DocumentType.PITCHING_DECK,
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


def call_llm(text: str, page_count: int = 1, text_length: int = 0, table_count: int = 0) -> dict:
    """Always use OpenRouter (Qwen) for classification.
    Azure OpenAI gpt-5-mini is a reasoning model — too slow and has API restrictions.
    Azure OpenAI is reserved for embeddings only.
    """
    return call_openrouter(text, page_count, text_length, table_count)


@traceable(name="classifier_azure_openai", run_type="llm")
def call_azure_openai(text: str, page_count: int = 1, text_length: int = 0, table_count: int = 0) -> dict:
    """Call Azure OpenAI gpt-4o for classification."""
    from openai import AzureOpenAI

    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    api_key = os.environ["AZURE_OPENAI_KEY"]
    deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o")

    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version="2025-01-01-preview",
    )

    prompt = CLASSIFY_PROMPT.format(
        text=text,
        page_count=page_count,
        text_length=text_length,
        table_count=table_count,
    )

    response = client.chat.completions.create(
        model=deployment,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=150,
    )

    run_tree = get_current_run_tree()
    if run_tree and response.usage:
        run_tree.extra = run_tree.extra or {}
        run_tree.extra["usage_metadata"] = {
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

    content = response.choices[0].message.content
    return parse_json_response(content)


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
        "model": "qwen/qwen-2.5-72b-instruct",  # Alibaba model - works in HK, excellent JSON output
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 150,
        "temperature": 0,  # Zero temp for deterministic classification
    }

    with httpx.Client(timeout=30) as client:
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
