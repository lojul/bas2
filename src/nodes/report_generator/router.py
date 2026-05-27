"""Report intent detection and parameter parsing."""

import re
from dataclasses import dataclass
from typing import Optional

from langsmith import traceable


@dataclass
class ReportRequest:
    """Parsed report request from user query."""
    report_type: Optional[str] = None  # rent, availability, market, pipeline, contacts
    district: Optional[str] = None     # Normalized to Chinese
    district_en: Optional[str] = None  # English name for display
    property_type: Optional[str] = None  # office, retail, industrial
    raw_query: str = ""                # Original user input


# Report type keywords
REPORT_KEYWORDS = {
    "zh": [
        "報告", "報表", "生成", "製作", "整理",
        "分析", "統計", "匯報", "匯總",
    ],
    "en": [
        "report", "generate", "create", "make",
        "analysis", "summary", "compile",
    ]
}

# Report type detection
REPORT_TYPE_PATTERNS = {
    "rent": [
        "租金", "呎租", "租", "rent", "rental", "price",
    ],
    "availability": [
        "空置", "可租", "有什麼", "有咩", "邊度有", "available", "vacancy", "vacant",
    ],
    "market": [
        "市場", "概覽", "趨勢", "market", "overview", "trend",
    ],
    "pipeline": [
        "發展", "項目", "新盤", "pipeline", "development", "project",
    ],
    "contacts": [
        "聯絡", "代理", "經紀", "contact", "agent", "broker",
    ],
}

# District mappings (Chinese canonical → English)
DISTRICTS = {
    # Hong Kong Island
    "中環": "Central",
    "金鐘": "Admiralty",
    "灣仔": "Wan Chai",
    "銅鑼灣": "Causeway Bay",
    "北角": "North Point",
    "鰂魚涌": "Quarry Bay",
    "太古": "Tai Koo",
    "西灣河": "Sai Wan Ho",
    "筲箕灣": "Shau Kei Wan",
    "柴灣": "Chai Wan",
    "上環": "Sheung Wan",
    "西營盤": "Sai Ying Pun",
    "堅尼地城": "Kennedy Town",
    "香港仔": "Aberdeen",
    "黃竹坑": "Wong Chuk Hang",
    # Kowloon
    "尖沙咀": "Tsim Sha Tsui",
    "佐敦": "Jordan",
    "油麻地": "Yau Ma Tei",
    "旺角": "Mong Kok",
    "太子": "Prince Edward",
    "深水埗": "Sham Shui Po",
    "長沙灣": "Cheung Sha Wan",
    "荔枝角": "Lai Chi Kok",
    "九龍灣": "Kowloon Bay",
    "觀塘": "Kwun Tong",
    "牛頭角": "Ngau Tau Kok",
    "藍田": "Lam Tin",
    "油塘": "Yau Tong",
    "將軍澳": "Tseung Kwan O",
    "九龍城": "Kowloon City",
    "土瓜灣": "To Kwa Wan",
    "紅磡": "Hung Hom",
    "黃大仙": "Wong Tai Sin",
    "鑽石山": "Diamond Hill",
    "新蒲崗": "San Po Kong",
    # New Territories
    "葵涌": "Kwai Chung",
    "葵芳": "Kwai Fong",
    "荃灣": "Tsuen Wan",
    "青衣": "Tsing Yi",
    "沙田": "Sha Tin",
    "火炭": "Fo Tan",
    "大圍": "Tai Wai",
    "馬鞍山": "Ma On Shan",
    "大埔": "Tai Po",
    "粉嶺": "Fanling",
    "上水": "Sheung Shui",
    "元朗": "Yuen Long",
    "天水圍": "Tin Shui Wai",
    "屯門": "Tuen Mun",
}

# Reverse mapping (English → Chinese)
DISTRICTS_EN_TO_ZH = {v.lower(): k for k, v in DISTRICTS.items()}

# Property type mappings
PROPERTY_TYPES = {
    "office": ["寫字樓", "辦公室", "office"],
    "retail": ["商舖", "零售", "店舖", "retail", "shop"],
    "industrial": ["工廈", "工業", "倉庫", "industrial", "warehouse"],
    "residential": ["住宅", "公寓", "residential", "apartment"],
}


@traceable(name="detect_report_intent", run_type="chain")
def detect_report_intent(query: str) -> bool:
    """Check if the query is requesting a report.

    Returns:
        True if query is a report request, False otherwise
    """
    query_lower = query.lower()

    # Check for report keywords
    all_keywords = REPORT_KEYWORDS["zh"] + REPORT_KEYWORDS["en"]
    has_report_keyword = any(kw in query_lower for kw in all_keywords)

    if not has_report_keyword:
        return False

    # Check for report type indicators
    for patterns in REPORT_TYPE_PATTERNS.values():
        if any(p in query_lower for p in patterns):
            return True

    # If has report keyword + district, likely a report request
    for district_zh in DISTRICTS:
        if district_zh in query:
            return True
    for district_en in DISTRICTS.values():
        if district_en.lower() in query_lower:
            return True

    return False


@traceable(name="parse_report_request", run_type="chain")
def parse_report_request(query: str) -> ReportRequest:
    """Parse report parameters from user query.

    Args:
        query: User's natural language query

    Returns:
        ReportRequest with extracted parameters
    """
    request = ReportRequest(raw_query=query)
    query_lower = query.lower()

    # 1. Detect report type
    for report_type, patterns in REPORT_TYPE_PATTERNS.items():
        if any(p in query_lower for p in patterns):
            request.report_type = report_type
            break

    # Default to rent analysis if not specified
    if not request.report_type:
        request.report_type = "rent"

    # 2. Extract district
    # Try Chinese first
    for district_zh, district_en in DISTRICTS.items():
        if district_zh in query:
            request.district = district_zh
            request.district_en = district_en
            break

    # Try English if no Chinese match
    if not request.district:
        for district_en_lower, district_zh in DISTRICTS_EN_TO_ZH.items():
            if district_en_lower in query_lower:
                request.district = district_zh
                request.district_en = DISTRICTS[district_zh]
                break

    # 3. Extract property type
    for prop_type, keywords in PROPERTY_TYPES.items():
        if any(kw in query_lower for kw in keywords):
            request.property_type = prop_type
            break

    return request


def get_report_type_display(report_type: str, lang: str = "zh") -> str:
    """Get display name for report type."""
    names = {
        "rent": {"zh": "租金分析報告", "en": "Rent Analysis Report"},
        "availability": {"zh": "空置單位報告", "en": "Availability Report"},
        "market": {"zh": "市場概覽報告", "en": "Market Overview Report"},
        "pipeline": {"zh": "發展項目報告", "en": "Development Pipeline Report"},
        "contacts": {"zh": "聯絡人名錄", "en": "Contact Directory"},
    }
    return names.get(report_type, {}).get(lang, report_type)
