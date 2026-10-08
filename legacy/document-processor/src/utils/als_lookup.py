"""Hong Kong Address Lookup Service (ALS) utility.

Normalises building names and returns a stable GeoAddress ID for deduplication.
API: https://www.als.gov.hk/lookup?q=<query>&n=3&lang=zh_TW

Fails open — callers must handle None return gracefully.
"""

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

ALS_URL = "https://www.als.gov.hk/lookup"
MIN_CONFIDENCE = 60.0

# ALS returns District Council districts (broad); map to Odoo selection values.
# Where a DC district spans multiple sub-districts, pick the most commercial one.
ALS_DISTRICT_MAP: dict[str, str] = {
    "中西區": "central",          # Central & Western → 中環
    "灣仔區": "wan_chai",
    "東區": "quarry_bay",          # 北角/鰂魚涌/太古/柴灣
    "南區": "other",
    "油尖旺區": "tsim_sha_tsui",   # 尖沙咀/旺角/油麻地
    "深水埗區": "cheung_sha_wan",  # 長沙灣/深水埗
    "九龍城區": "hung_hom",        # 紅磡/土瓜灣
    "觀塘區": "kwun_tong",
    "黃大仙區": "wong_tai_sin",
    "葵青區": "kwai_chung",
    "荃灣區": "tsuen_wan",
    "屯門區": "tuen_mun",
    "元朗區": "yuen_long",
    "沙田區": "sha_tin",
    "大埔區": "tai_po",
    "西貢區": "tseung_kwan_o",
    "北區": "other",
    "離島區": "other",
}


@dataclass
class BuildingInfo:
    geo_id: str             # ALS GeoAddress — stable unique dedup key
    name_zh: str            # Canonical Chinese building name
    name_en: str            # Canonical English building name
    address_zh: str         # Full Chinese street address
    address_en: str         # Full English street address
    district_zh: str        # DC district from ALS (e.g. 觀塘區)
    district_odoo: str | None  # Mapped to Odoo selection value
    lat: float | None
    lng: float | None
    confidence: float


def lookup_building(query: str, timeout: int = 5) -> BuildingInfo | None:
    """Look up a building by name or address via ALS API.

    Returns the best match if confidence >= 60, otherwise None.
    Returns None (does not raise) on network or parse errors.
    """
    if not query or not query.strip():
        return None

    try:
        resp = httpx.get(
            ALS_URL,
            params={"q": query.strip(), "n": 3, "lang": "zh_TW"},
            timeout=timeout,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.warning("ALS lookup failed for '%s': %s", query, e)
        return None

    try:
        return _parse_xml(resp.text)
    except Exception as e:
        logger.warning("ALS parse error for '%s': %s", query, e)
        return None


def _parse_xml(xml_text: str) -> BuildingInfo | None:
    root = ET.fromstring(xml_text)
    suggestions = root.findall(".//SuggestedAddress")
    if not suggestions:
        return None

    first = suggestions[0]

    score_el = first.find(".//Score")
    score = float(score_el.text) if score_el is not None else 0.0
    if score < MIN_CONFIDENCE:
        return None

    premises = first.find(".//PremisesAddress")
    if premises is None:
        return None

    # Chinese components
    chi = premises.find("ChiPremisesAddress")
    chi_building = _text(chi, "BuildingName")
    chi_street = _text(chi, "ChiStreet/StreetName")
    chi_from = _text(chi, "ChiStreet/BuildingNoFrom")
    chi_to = _text(chi, "ChiStreet/BuildingNoTo")
    chi_district = _text(chi, "ChiDistrict/DcDistrict")

    if chi_from and chi_to and chi_from != chi_to:
        chi_addr = f"{chi_street} {chi_from}-{chi_to}號"
    elif chi_from:
        chi_addr = f"{chi_street} {chi_from}號"
    else:
        chi_addr = chi_street
    if chi_building and chi_addr:
        chi_full = f"{chi_addr} {chi_building}"
    else:
        chi_full = chi_building or chi_addr

    # English components
    eng = premises.find("EngPremisesAddress")
    eng_building = _text(eng, "BuildingName")
    eng_street = _text(eng, "EngStreet/StreetName")
    eng_from = _text(eng, "EngStreet/BuildingNoFrom")
    eng_to = _text(eng, "EngStreet/BuildingNoTo")

    if eng_from and eng_to and eng_from != eng_to:
        eng_addr = f"{eng_from}-{eng_to} {eng_street}"
    elif eng_from:
        eng_addr = f"{eng_from} {eng_street}"
    else:
        eng_addr = eng_street

    # GeoAddress + coordinates
    geo_id = _text(premises, "GeoAddress")
    geo = premises.find("GeospatialInformation")
    lat = _float(geo, "Latitude")
    lng = _float(geo, "Longitude")

    return BuildingInfo(
        geo_id=geo_id,
        name_zh=chi_building or chi_addr,
        name_en=eng_building or eng_addr,
        address_zh=chi_full,
        address_en=eng_addr,
        district_zh=chi_district,
        district_odoo=ALS_DISTRICT_MAP.get(chi_district),
        lat=lat,
        lng=lng,
        confidence=score,
    )


def _text(el, path: str) -> str:
    if el is None:
        return ""
    found = el.find(path)
    return (found.text or "").strip() if found is not None else ""


def _float(el, path: str) -> float | None:
    val = _text(el, path)
    try:
        return float(val) if val else None
    except ValueError:
        return None
