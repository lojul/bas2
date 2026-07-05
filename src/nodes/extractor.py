"""Document data extractor using OpenRouter AI."""

import os
import httpx
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree

from src.state import DocumentState, DocumentType, ProcessingStatus, ExtractedData
from src.utils.json_parser import parse_json_response


# Hong Kong districts for extraction hints
HK_DISTRICTS = """
Hong Kong Island: 中環/Central, 金鐘/Admiralty, 灣仔/Wan Chai, 銅鑼灣/Causeway Bay, 北角/North Point,
鰂魚涌/Quarry Bay, 太古/Tai Koo, 柴灣/Chai Wan, 上環/Sheung Wan, 黃竹坑/Wong Chuk Hang
Kowloon: 尖沙咀/Tsim Sha Tsui, 佐敦/Jordan, 油麻地/Yau Ma Tei, 旺角/Mong Kok, 深水埗/Sham Shui Po,
長沙灣/Cheung Sha Wan, 九龍灣/Kowloon Bay, 觀塘/Kwun Tong, 牛頭角/Ngau Tau Kok, 紅磡/Hung Hom,
新蒲崗/San Po Kong, 黃大仙/Wong Tai Sin, 土瓜灣/To Kwa Wan
New Territories: 葵涌/Kwai Chung, 荃灣/Tsuen Wan, 沙田/Sha Tin, 火炭/Fo Tan, 大埔/Tai Po,
元朗/Yuen Long, 屯門/Tuen Mun, 將軍澳/Tseung Kwan O, 馬鞍山/Ma On Shan
"""

# Extraction prompts for each document type
PROMPTS = {
    DocumentType.LISTING: """Extract the MAIN property listing data from this document.

IMPORTANT RULES:
- ONLY extract data that is EXPLICITLY stated in the text
- If a field is NOT found in the text, use null (not empty string, not made-up data)
- DO NOT invent or hallucinate any information
- If this text does NOT contain property listing information, return {{"_no_data": true}}

DISTRICT DETECTION - Look for these Hong Kong districts in the address or text:
""" + HK_DISTRICTS + """

TEXT:
{text}

Return a SINGLE JSON object (NOT an array):
{{
  "building_name": "name from text or null",
  "address": "full address from text or null",
  "district": "Hong Kong district from text/address (use Chinese name like 沙田, 觀塘, 中環) or null",
  "property_type": "office/retail/residential/industrial or null",
  "size_sqft": number from text or null,
  "rent_monthly": number from text or null,
  "floor": "floor from text or null",
  "unit": "unit from text or null",
  "contact_name": "agent name from text or null",
  "contact_phone": "phone number from text or null",
  "listing_ref": "listing reference number (樓盤編號 / 編號 / ref no, e.g. #10978) or null",
  "headline": "the ad's own title/headline if present (e.g. 中環旺舖推介) or null"
}}

Return ONLY the JSON object, no array, no explanation:""",

    DocumentType.LISTING_LIST: """Extract ALL property listings from this document.

The document is one of TWO formats — detect which and extract accordingly:
FORMAT A — TABLE: one building with many floors/units in a table.
FORMAT B — FLYER COLLECTION: multiple separate property advertisements (different buildings,
different addresses), often one or two flyers per page. Each flyer has its own 物業地址,
面積, 放租/放售 price.

IMPORTANT RULES:
- ONLY extract data that is EXPLICITLY stated in the text
- If a field is NOT found in the text, use null (not empty string, not made-up data)
- DO NOT invent or hallucinate any information
- Documents may list RENT (月租/租金/放租) OR SALE prices (售價/賣價/放售) or both
- If this text does NOT contain property listing information, return {{"_no_data": true}}

UNIT EXTRACTION RULES (critical):
- Extract EVERY individual property/floor/unit as a SEPARATE entry in the units array
- FORMAT A: one table row = one unit entry; building fields go at top level
- FORMAT B: one flyer/advertisement = one unit entry; put each property's OWN
  building_name, address, and district INSIDE its unit entry (top-level building
  fields stay null). Scan ALL pages — do not stop after the first property.
- If a price was crossed out and replaced (e.g. HK$13,800 → HK$12,000), use the FINAL price
- SKIP any "Total", "Sub-total", "合計", "總計", "全棟" or aggregate summary rows
- COUNT the properties in the document; the units array must have the same number of entries
- property_type per unit: 地舖 (G/F street shop), 商舖 (mall/arcade shop), 寫字樓 (office),
  工廈 (industrial), 住宅 (residential) — infer from context like G/F, 商場, 舖

CONTACT EXTRACTION (do not skip):
- Agent names and phones usually appear in page FOOTERS, e.g. "可致電 2753 9862 何小姐 或 9844 6661 譚小姐洽"
- Extract them into top-level contact_name and contact_phone
- Multiple agents: join with 、 e.g. contact_name "何小姐、譚小姐", contact_phone "2753 9862、9844 6661"

BUILDING SUMMARY RULES (FORMAT A only):
- Whole-building asking price (整幢售價, 全棟售價) → "asking_price"
- Total current rental income (月租收入, 全棟月租) → "rental_income"

DISTRICT DETECTION - Look for these Hong Kong districts in the address or text:
""" + HK_DISTRICTS + """

TEXT:
{text}

Return JSON (max 20 units):
{{
  "building_name": "FORMAT A: building name; FORMAT B: null",
  "address": "FORMAT A: address; FORMAT B: null",
  "district": "FORMAT A: district (Chinese name like 沙田, 觀塘); FORMAT B: null",
  "contact_phone": "phone from text or null",
  "contact_name": "agent name from text or null",
  "asking_price": whole building sale price as number or null,
  "rental_income": total monthly rental income as number or null,
  "units": [
    {{
      "building_name": "FORMAT B: this property's building or null",
      "address": "FORMAT B: this property's full address or null",
      "district": "FORMAT B: this property's district or null",
      "property_type": "地舖/商舖/寫字樓/工廈/住宅 or null",
      "floor": "floor or null",
      "unit": "unit/shop number or null",
      "size": size in sqft as number or null,
      "rent": monthly rent as number or null,
      "price": sale price as number or null,
      "features": "brief notes e.g. 全不包, 連閣樓, 前租客 or null"
    }}
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

DISTRICT DETECTION - Look for these Hong Kong districts:
""" + HK_DISTRICTS + """

TEXT:
{text}

Return a JSON object with ALL available information:
{{
  "project_name": "project/building name",
  "project_name_zh": "Chinese name if available",
  "developer": "developer company name",
  "address": "full address",
  "district": "Hong Kong district (use Chinese name like 北角, 中環, 觀塘) or null",
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
        # For pitching decks, sample from multiple parts of the document
        # Key data is often in middle (project summary) and end (leasing details)
        if doc_type == DocumentType.PITCHING_DECK and len(full_text) > 20000:
            # Sample: first 8K + middle 8K + last 8K = 24K total
            text_start = full_text[:8000]
            middle_start = len(full_text) // 3
            text_middle = full_text[middle_start:middle_start + 8000]
            text_end = full_text[-8000:]
            text_sample = text_start + "\n\n... [MIDDLE SECTION] ...\n\n" + text_middle + "\n\n... [END SECTION] ...\n\n" + text_end
        else:
            # For other types, use first 16000 chars
            text_sample = full_text[:16000]

        prompt = prompt_template.format(text=text_sample)

        # Extraction memory (Phase 1): show the LLM how similar past documents
        # were extracted — teaser ads, flyers etc. share formats, so one good
        # past extraction teaches the pattern without any code change.
        examples = fetch_examples(text_sample, doc_type)
        if examples:
            prompt = examples + "\n\n" + prompt

        try:
            result = call_llm(prompt)
        except ValueError as parse_err:
            # JSON parse failed — retry once with a stricter JSON-only instruction
            retry_prompt = prompt + "\n\nCRITICAL: Your previous response could not be parsed as JSON. Return ONLY raw JSON — no markdown fences, no ```json, no explanation, no trailing text."
            result = call_llm(retry_prompt)

        state.extracted = ExtractedData(
            raw=result,
            document_type=doc_type,
        )
        state.update_status(ProcessingStatus.EXTRACTED)

    except ValueError as e:
        # JSON parsing error on both attempts - store error info but don't fail silently
        state.extracted = ExtractedData(
            raw={"_extraction_failed": True, "_error": str(e)},
            document_type=doc_type
        )
        state.set_error(f"Extraction parse error (after retry): {str(e)}")

    except httpx.HTTPStatusError as e:
        state.extracted = ExtractedData(raw={}, document_type=doc_type)
        state.set_error(f"Extraction API error: {e.response.status_code}")

    except Exception as e:
        state.extracted = ExtractedData(raw={}, document_type=doc_type)
        state.set_error(f"Extraction error: {str(e)}")

    return state


def fetch_examples(text_sample: str, doc_type: DocumentType, top: int = 2) -> str:
    """Extraction memory (Phase 1): retrieve up to `top` similar past extractions
    of the same document type from Azure AI Search and format them as few-shot
    examples. Fails open (returns "") on any error — extraction must never break
    because the example lookup did.
    """
    import os

    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT", "")
    api_key = os.environ.get("AZURE_SEARCH_API_KEY", "")
    index = os.environ.get("AZURE_SEARCH_INDEX", "processed-documents")
    if not endpoint or not api_key:
        return ""

    try:
        with httpx.Client(timeout=8) as client:
            resp = client.post(
                f"{endpoint}/indexes/{index}/docs/search?api-version=2024-07-01",
                headers={"api-key": api_key},
                json={
                    "search": text_sample[:800],
                    "filter": f"document_type eq '{doc_type.value}'",
                    "select": "file_name,extracted_data",
                    "top": top,
                },
            )
            if resp.status_code != 200:
                return ""
            docs = resp.json().get("value", [])
    except Exception:
        return ""

    examples = []
    for doc in docs:
        data = (doc.get("extracted_data") or "").strip()
        if not data or data in ("{}", "null") or "_extraction_failed" in data:
            continue
        examples.append(data[:1200])

    if not examples:
        return ""

    blocks = "\n\n".join(f"Example {i + 1}:\n{e}" for i, e in enumerate(examples))
    return (
        "REFERENCE — here is how similar documents of this type were previously "
        "extracted (follow the same field usage and formatting, but extract ONLY "
        "from the TEXT below, never copy values from these examples):\n\n" + blocks
    )


def call_llm(prompt: str) -> dict:
    """Always use OpenRouter (Qwen) for extraction.
    Azure OpenAI gpt-5-mini is a reasoning model — too slow and has API restrictions.
    Azure OpenAI is reserved for embeddings only.
    """
    return call_openrouter(prompt)


@traceable(name="extractor_azure_openai", run_type="llm")
def call_azure_openai(prompt: str) -> dict:
    """Call Azure OpenAI gpt-5-mini for extraction."""
    from src.utils.llm import chat_complete
    from src.utils.json_parser import parse_json_response
    content = chat_complete(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4000,
    )
    return parse_json_response(content)


@traceable(name="extractor_openrouter", run_type="llm")
def call_openrouter(prompt: str) -> dict:
    """Call OpenRouter API for extraction.

    Args:
        prompt: Full prompt with text

    Returns:
        Extracted data dict
    """
    from src.utils.llm import openrouter_chat
    data = openrouter_chat(prompt, max_tokens=4000, temperature=0.0)

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
