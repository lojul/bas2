"""Validate report parameters and generate prompts for missing info."""

from typing import Optional
from dataclasses import dataclass

from langsmith import traceable

from .router import ReportRequest, DISTRICTS, REPORT_TYPE_PATTERNS, get_report_type_display


@dataclass
class ValidationResult:
    """Result of report request validation."""
    is_valid: bool
    missing_params: list[str]
    prompt_message: Optional[str] = None  # Message to ask user for missing params


# Report types that require district
DISTRICT_REQUIRED = ["rent", "availability", "market", "contacts"]

# Report types that can work with developer instead of district
DEVELOPER_OR_DISTRICT = ["pipeline"]


@traceable(name="validate_report_request", run_type="chain")
def validate_request(request: ReportRequest) -> ValidationResult:
    """Validate that all required parameters are present.

    Args:
        request: Parsed report request

    Returns:
        ValidationResult indicating if request is valid
    """
    missing = []

    # Check report type
    if not request.report_type:
        missing.append("report_type")

    # Check district for reports that need it
    if request.report_type in DISTRICT_REQUIRED:
        if not request.district:
            missing.append("district")

    # Pipeline can use district OR developer
    if request.report_type in DEVELOPER_OR_DISTRICT:
        if not request.district:
            missing.append("district")  # Can also be developer, but we'll use district for now

    if missing:
        return ValidationResult(
            is_valid=False,
            missing_params=missing,
            prompt_message=get_missing_params_prompt(request, missing)
        )

    return ValidationResult(is_valid=True, missing_params=[])


def get_missing_params_prompt(request: ReportRequest, missing: list[str]) -> str:
    """Generate user-friendly prompt for missing parameters.

    Args:
        request: The partial report request
        missing: List of missing parameter names

    Returns:
        Bilingual prompt message
    """
    # Detect language from query
    is_chinese = any('\u4e00' <= c <= '\u9fff' for c in request.raw_query)

    if "report_type" in missing:
        if is_chinese:
            return _get_report_type_menu_zh(request.district)
        return _get_report_type_menu_en(request.district_en)

    if "district" in missing:
        if is_chinese:
            return _get_district_menu_zh(request.report_type)
        return _get_district_menu_en(request.report_type)

    return "請提供更多資訊 / Please provide more information"


def _get_report_type_menu_zh(district: Optional[str]) -> str:
    """Generate Chinese menu for report type selection."""
    location = f"{district}區" if district else ""
    return f"""我可以為你生成以下{location}報告：

1. 📊 **租金分析報告** - 平均租金、呎租比較、大廈分析
2. 🏢 **空置單位報告** - 現有空置單位、面積、聯絡方式
3. 📰 **市場概覽報告** - 市場趨勢、新聞、庫存摘要
4. 🏗️ **發展項目報告** - 新發展項目、總樓面面積
5. 📇 **聯絡人名錄** - 代理/經紀聯絡資料

請回覆數字或報告名稱選擇。"""


def _get_report_type_menu_en(district: Optional[str]) -> str:
    """Generate English menu for report type selection."""
    location = f"for {district} " if district else ""
    return f"""I can generate these reports {location}:

1. 📊 **Rent Analysis** - Average rent, price/sqft comparison, building analysis
2. 🏢 **Availability Report** - Current vacant units, sizes, contacts
3. 📰 **Market Overview** - Market trends, news, inventory summary
4. 🏗️ **Development Pipeline** - New projects, GFA breakdown
5. 📇 **Contact Directory** - Agent/broker contact details

Reply with a number or report name to select."""


def _get_district_menu_zh(report_type: Optional[str]) -> str:
    """Generate Chinese menu for district selection."""
    report_name = get_report_type_display(report_type, "zh") if report_type else "報告"

    districts_by_area = {
        "港島": ["中環", "金鐘", "灣仔", "銅鑼灣", "北角", "鰂魚涌", "上環", "黃竹坑"],
        "九龍": ["尖沙咀", "旺角", "九龍灣", "觀塘", "紅磡", "長沙灣"],
        "新界": ["荃灣", "葵涌", "沙田", "大埔", "元朗", "屯門"],
    }

    lines = [f"請選擇地區以生成 **{report_name}**：\n"]
    for area, districts in districts_by_area.items():
        lines.append(f"**{area}**: {', '.join(districts)}")

    return "\n".join(lines)


def _get_district_menu_en(report_type: Optional[str]) -> str:
    """Generate English menu for district selection."""
    report_name = get_report_type_display(report_type, "en") if report_type else "report"

    districts_by_area = {
        "Hong Kong Island": ["Central", "Admiralty", "Wan Chai", "Causeway Bay", "North Point", "Quarry Bay"],
        "Kowloon": ["Tsim Sha Tsui", "Mong Kok", "Kowloon Bay", "Kwun Tong", "Hung Hom"],
        "New Territories": ["Tsuen Wan", "Kwai Chung", "Sha Tin", "Tai Po", "Yuen Long", "Tuen Mun"],
    }

    lines = [f"Please select a district for the **{report_name}**:\n"]
    for area, districts in districts_by_area.items():
        lines.append(f"**{area}**: {', '.join(districts)}")

    return "\n".join(lines)
