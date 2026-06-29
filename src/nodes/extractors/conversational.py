"""Conversational extraction path — single-pass LangChain extractor.

Used for: free-text / WhatsApp-style documents with multiple properties,
emoji separators, no tables, or plain DOCX prose.

Architecture:
  Single pass — LLM reads the full document and returns ALL properties
                in one JSON response, with per-field confidence scores.
  Output      — list of property dicts stored in extracted.raw["properties"]

Why single-pass?
  The previous two-pass approach (segment then extract per segment) made N+1
  LLM calls and was vulnerable to over-segmentation — the regex fallback split
  on internal separator lines (e.g. between floor listings), producing many
  duplicate or broken segments. A single call is cheaper and more accurate
  because the model sees the full document context when deciding boundaries.
"""

import os
import logging
from typing import Any

from langsmith import traceable
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.state import DocumentState, ExtractedData, DocumentType, ProcessingStatus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class FloorUnit(BaseModel):
    """A single floor or unit within a property."""
    floor: str | None = None
    unit: str | None = None
    size_sqft: int | None = None
    sell_price: int | None = None
    rent_monthly: int | None = None
    notes: str | None = None


class ExtractedProperty(BaseModel):
    """One property entity extracted from the document."""
    building_name: str | None = Field(None, description="Building or project name")
    address: str | None = Field(None, description="Full street address")
    district: str | None = Field(None, description="HK district in Chinese e.g. 旺角, 中環")
    property_type: str | None = Field(None, description="office / retail / residential / industrial / mixed")

    transaction_type: str | None = Field(None, description="sale / lease / both")
    sell_price: int | None = Field(None, description="Sale price in HKD (integer)")
    rent_monthly: int | None = Field(None, description="Monthly rent in HKD (integer)")
    return_rate: float | None = Field(None, description="Gross yield as decimal e.g. 0.038 for 3.8%")
    ownership_pct: float | None = Field(None, description="Ownership percentage e.g. 0.8 for 80%")

    floor_units: list[FloorUnit] = Field(default_factory=list)

    contact_name: str | None = None
    contact_phone: str | None = None
    notes: str | None = None

    overall_confidence: float = Field(0.5, ge=0.0, le=1.0)
    field_confidence: dict[str, float] = Field(default_factory=dict)


class MultiExtractionOutput(BaseModel):
    """All properties extracted from a document in one pass."""
    properties: list[ExtractedProperty] = Field(default_factory=list)
    shared_contact_name: str | None = None
    shared_contact_phone: str | None = None


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

EXTRACT_ALL_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are extracting ALL property listings from a Hong Kong property document. "
     "Extract every distinct property/address. Return null for missing fields. "
     "Do NOT hallucinate.\n\n"
     "CHINESE NUMBER PARSING — convert to integer HKD:\n"
     "  億 = 100,000,000 | 萬 = 10,000\n"
     "  Examples: 4億6000萬 = 460000000 | 9800萬 = 98000000 | 2億9780萬 = 297800000\n\n"
     "TRANSACTION TYPE RULES:\n"
     "  - 售價/出售/賣 → transaction_type='sale', put price in sell_price\n"
     "  - 招租/出租/月租 → transaction_type='lease', put price in rent_monthly\n"
     "  - When transaction_type='sale': any 每月租金/租金收入 figure is the CURRENT "
     "tenant income (the investment yield reference). Put it in rent_monthly so the "
     "return_rate can be verified; also note it in the notes field as "
     "'Current monthly rental income: HK$[amount] (investment yield reference)'.\n\n"
     "HK districts: 中環/Central 金鐘/Admiralty 灣仔/Wan Chai 銅鑼灣/Causeway Bay "
     "北角/North Point 上環/Sheung Wan 尖沙咀/Tsim Sha Tsui 佐敦/Jordan "
     "油麻地/Yau Ma Tei 旺角/Mong Kok 深水埗/Sham Shui Po 九龍灣/Kowloon Bay "
     "觀塘/Kwun Tong 荃灣/Tsuen Wan 沙田/Sha Tin 將軍澳/Tseung Kwan O"),
    ("human",
     """Extract ALL property listings from this {document_type} document.

TEXT:
---
{text}
---

Rules:
- Each DISTINCT building/address = one entry in the "properties" array
- Floors or units within the SAME building → put in that property's floor_units[]
- Do NOT create a separate property entry for each floor
- If one contact applies to ALL properties, put it in shared_contact_name / shared_contact_phone
- Parse Chinese numbers carefully (億/萬 → integer HKD)

Return JSON:
{{
  "properties": [
    {{
      "building_name": "string or null",
      "address": "string or null",
      "district": "Chinese district name or null",
      "property_type": "office/retail/residential/industrial/mixed or null",
      "transaction_type": "sale/lease/both or null",
      "sell_price": integer HKD or null,
      "rent_monthly": integer HKD/month or null,
      "return_rate": decimal e.g. 0.038 for 3.8% or null,
      "ownership_pct": decimal e.g. 0.8 for 80% or null,
      "floor_units": [
        {{"floor": "2/F", "unit": null, "size_sqft": null, "sell_price": null, "rent_monthly": null, "notes": null}}
      ],
      "contact_name": "string or null",
      "contact_phone": "string or null",
      "notes": "string or null",
      "overall_confidence": 0.0-1.0,
      "field_confidence": {{"building_name": 0.9, "address": 0.8, "sell_price": 0.7}}
    }}
  ],
  "shared_contact_name": "string or null",
  "shared_contact_phone": "string or null"
}}

Return ONLY valid JSON."""),
])


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------

def _get_llm():
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not configured")
    return ChatOpenAI(
        model="qwen/qwen-2.5-72b-instruct",
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        temperature=0,
        max_tokens=4000,
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

@traceable(name="extract_conversational", run_type="chain")
def extract_conversational(state: DocumentState) -> DocumentState:
    """Single-pass conversational extraction for free-text multi-property documents.

    Sends the full document text to the LLM once and asks it to return all
    properties as a JSON array. This replaces the previous two-pass approach
    (segment then extract per segment) which made N+1 LLM calls and was prone
    to over-segmentation errors.
    """
    state.update_status(ProcessingStatus.EXTRACTING)

    text = state.ocr.text if state.ocr else ""
    if not text:
        state.extracted = ExtractedData(raw={}, document_type=state.document_type)
        state.update_status(ProcessingStatus.EXTRACTED)
        return state

    try:
        llm = _get_llm()
        doc_type_str = state.document_type.value if state.document_type else "listing_list"

        chain = EXTRACT_ALL_PROMPT | llm.with_structured_output(MultiExtractionOutput, method="json_mode")
        result: MultiExtractionOutput = chain.invoke({
            "text": text[:10000],
            "document_type": doc_type_str,
        })

        properties: list[dict[str, Any]] = []
        for prop in result.properties:
            p = prop.model_dump()
            if not p.get("contact_name") and result.shared_contact_name:
                p["contact_name"] = result.shared_contact_name
            if not p.get("contact_phone") and result.shared_contact_phone:
                p["contact_phone"] = result.shared_contact_phone
            # Deterministically generate rental income note for sale properties
            if p.get("transaction_type") == "sale" and p.get("rent_monthly"):
                income = p["rent_monthly"]
                expected_note = f"Current monthly rental income: HK${income:,} (investment yield reference)"
                existing_note = p.get("notes") or ""
                if "monthly rental income" not in existing_note.lower():
                    p["notes"] = (existing_note + " " + expected_note).strip()
            properties.append(p)

        logger.info(
            "Conversational extraction: %d properties found in '%s'",
            len(properties), state.file_name,
        )

        # ── Aggregate confidence ───────────────────────────────────────────────
        confidence_scores = [float(p.get("overall_confidence", 0.5)) for p in properties]
        overall_confidence = (
            sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.5
        )

        all_field_keys: set[str] = set()
        for p in properties:
            all_field_keys.update(p.get("field_confidence", {}).keys())

        merged_field_confidence: dict[str, float] = {}
        for key in all_field_keys:
            vals = [p["field_confidence"][key] for p in properties if key in p.get("field_confidence", {})]
            if vals:
                merged_field_confidence[key] = sum(vals) / len(vals)

        raw: dict[str, Any] = {
            "properties": properties,
            "transaction_type": _first_value(properties, "transaction_type"),
            "extraction_path": "conversational",
            "property_count": len(properties),
        }

        # Flatten single-property docs to top level so dashboard code can read them
        if len(properties) == 1:
            p = properties[0]
            for field in ("building_name", "address", "district", "property_type",
                          "transaction_type", "sell_price", "rent_monthly",
                          "return_rate", "ownership_pct", "contact_name",
                          "contact_phone", "floor_units", "notes"):
                if p.get(field) is not None:
                    raw[field] = p[field]

        state.extracted = ExtractedData(
            raw=raw,
            document_type=state.document_type,
            field_confidence=merged_field_confidence,
            overall_confidence=overall_confidence,
        )
        state.update_status(ProcessingStatus.EXTRACTED)
        state.needs_review = overall_confidence < 0.75

        logger.info(
            "Conversational extraction complete: %d properties, confidence=%.2f, needs_review=%s",
            len(properties), overall_confidence, state.needs_review,
        )

    except Exception as e:
        logger.error("Conversational extraction error: %s", e)
        state.extracted = ExtractedData(
            raw={"_extraction_failed": True, "_error": str(e)},
            document_type=state.document_type,
        )
        state.set_error(f"Conversational extraction error: {e}")

    return state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_value(properties: list[dict], key: str) -> Any:
    for p in properties:
        v = p.get(key)
        if v is not None:
            return v
    return None
