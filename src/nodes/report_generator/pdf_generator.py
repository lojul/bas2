"""Generate PDF reports using FPDF2 (pure Python, no system dependencies).

This module generates professional PDF reports that work on:
- Azure Functions (consumption plan)
- Streamlit Cloud
- Any Python environment

No system dependencies required (unlike WeasyPrint which needs pango/cairo).
"""

import os
import io
import base64
import httpx
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from fpdf import FPDF
from fpdf.fonts import FontFace
from langsmith import traceable

from .router import ReportRequest, get_report_type_display
from .statistics import RentStatistics, AvailabilityStatistics


# Chinese font URL (hosted on Azure Blob Storage)
CHINESE_FONT_URL = "https://blobhk04472.blob.core.windows.net/fonts/wqy-microhei.ttc"
_cached_font_path: Optional[str] = None


def _get_chinese_font() -> Optional[str]:
    """Download and cache Chinese font from Azure Blob Storage.

    Returns path to cached font file, or None if download fails.
    """
    global _cached_font_path

    # Return cached path if already downloaded
    if _cached_font_path and Path(_cached_font_path).exists():
        return _cached_font_path

    # Check if font exists in temp directory
    temp_font_path = Path(tempfile.gettempdir()) / "wqy-microhei.ttc"
    if temp_font_path.exists() and temp_font_path.stat().st_size > 1000000:
        _cached_font_path = str(temp_font_path)
        return _cached_font_path

    # Download font
    try:
        response = httpx.get(CHINESE_FONT_URL, timeout=60, follow_redirects=True)
        if response.status_code == 200 and len(response.content) > 1000000:
            temp_font_path.write_bytes(response.content)
            _cached_font_path = str(temp_font_path)
            return _cached_font_path
    except Exception as e:
        print(f"Failed to download Chinese font: {e}")

    return None


@dataclass
class ReportOutput:
    """Generated report output."""
    title: str
    title_en: str
    report_type: str
    district: str
    district_en: str
    generated_at: datetime
    pdf_bytes: Optional[bytes] = None
    pdf_url: Optional[str] = None
    filename: str = ""
    document_count: int = 0
    summary_markdown: str = ""
    data: dict = field(default_factory=dict)
    error: Optional[str] = None


# Get assets directory
ASSETS_DIR = Path(__file__).parent / "assets"


class PropertyReportPDF(FPDF):
    """Custom PDF class for property reports."""

    def __init__(self, title_zh: str, title_en: str, logo_path: Optional[Path] = None):
        super().__init__()
        self.title_zh = title_zh
        self.title_en = title_en
        self.logo_path = logo_path

        # Colors (C21 Gold: #c9a227, Navy: #1a365d)
        self.gold = (201, 162, 39)
        self.navy = (26, 54, 93)
        self.light_gray = (247, 250, 252)
        self.gray = (113, 128, 150)

        # Load Chinese font if available
        self.has_chinese_font = False
        chinese_font_path = _get_chinese_font()
        if chinese_font_path:
            try:
                self.add_font("Chinese", "", chinese_font_path)
                self.has_chinese_font = True
            except Exception as e:
                print(f"Failed to load Chinese font: {e}")

        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        """Draw page header with logo and title."""
        # Logo (if exists)
        if self.logo_path and self.logo_path.exists():
            self.image(str(self.logo_path), 10, 8, 25)
            x_start = 40
        else:
            x_start = 10

        # Title (navy blue text on white background)
        self.set_xy(x_start, 10)
        self.set_text_color(*self.navy)
        self.set_font("Helvetica", "B", 18)
        self.cell(0, 8, self.title_en)

        self.set_xy(x_start, 20)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*self.gray)
        self.cell(0, 6, "Century 21 Property Intelligence Report")

        # Date on right
        self.set_xy(150, 12)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*self.gray)
        self.cell(0, 5, f"Generated: {datetime.now().strftime('%Y-%m-%d')}")

        # Gold line separator
        self.set_draw_color(*self.gold)
        self.set_line_width(0.5)
        self.line(10, 32, 200, 32)

        # Reset position
        self.set_xy(10, 40)
        self.set_text_color(0, 0, 0)

    def footer(self):
        """Draw page footer."""
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*self.gray)
        self.cell(0, 10, f"Century 21 Document Processor | Page {self.page_no()}", align="C")

    def section_title(self, title: str):
        """Draw a section title with gold underline."""
        self.ln(5)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*self.navy)
        self.cell(0, 8, title, ln=True)

        # Gold underline
        self.set_draw_color(*self.gold)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 60, self.get_y())
        self.ln(5)

    def stat_card(self, label: str, value: str, x: float, y: float, width: float = 45):
        """Draw a statistics card."""
        # Background
        self.set_fill_color(*self.light_gray)
        self.rect(x, y, width, 20, 'F')

        # Value
        self.set_xy(x, y + 3)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(*self.gold)
        self.cell(width, 8, value, align="C")

        # Label
        self.set_xy(x, y + 12)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*self.gray)
        self.cell(width, 5, label, align="C")

    def data_table(self, headers: list[str], rows: list[list[str]], col_widths: list[float] = None):
        """Draw a data table with Chinese font support."""
        if not col_widths:
            col_widths = [190 / len(headers)] * len(headers)

        # Header row
        self.set_fill_color(237, 242, 247)
        self.set_text_color(*self.navy)
        self.set_font("Helvetica", "B", 9)

        for i, header in enumerate(headers):
            self.cell(col_widths[i], 8, header, border=0, fill=True)
        self.ln()

        # Gold line under header
        self.set_draw_color(*self.gold)
        self.set_line_width(0.3)
        y = self.get_y()
        self.line(10, y, 200, y)

        # Data rows - use Chinese font if available
        if self.has_chinese_font:
            self.set_font("Chinese", "", 8)
        else:
            self.set_font("Helvetica", "", 8)
        self.set_text_color(45, 55, 72)

        for row_idx, row in enumerate(rows):
            # Alternate row colors
            if row_idx % 2 == 0:
                self.set_fill_color(255, 255, 255)
            else:
                self.set_fill_color(*self.light_gray)

            for i, cell in enumerate(row):
                # Truncate long text
                cell_text = str(cell)[:25] if len(str(cell)) > 25 else str(cell)
                self.cell(col_widths[i], 7, cell_text, border=0, fill=True)
            self.ln()

            # Light border
            self.set_draw_color(226, 232, 240)
            self.line(10, self.get_y(), 200, self.get_y())


def _safe_text(text: str, max_len: int = 50) -> str:
    """Clean text for PDF display.

    Keeps Chinese and English characters for display with Chinese font.
    """
    if not text:
        return ""

    text = str(text).strip()

    # Clean up multiple spaces
    text = ' '.join(text.split())

    return text[:max_len] if text else "N/A"


def _format_number(value) -> str:
    """Format number with commas."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value):,.0f}"
    except (ValueError, TypeError):
        return str(value)


def _format_currency(value) -> str:
    """Format as currency."""
    if value is None:
        return "N/A"
    try:
        return f"${float(value):,.0f}"
    except (ValueError, TypeError):
        return str(value)


@traceable(name="generate_pdf_report", run_type="chain")
def generate_pdf_report(
    request: ReportRequest,
    statistics: RentStatistics | AvailabilityStatistics,
    images: list[dict],
    document_count: int
) -> ReportOutput:
    """Generate PDF report from statistics and images.

    Args:
        request: Validated report request
        statistics: Computed statistics (RentStatistics or AvailabilityStatistics)
        images: List of image dicts {url, building, doc_id}
        document_count: Number of documents analyzed

    Returns:
        ReportOutput with PDF bytes and metadata
    """
    now = datetime.now()
    title_zh = f"{request.district}區{get_report_type_display(request.report_type, 'zh')}"
    title_en = f"{request.district_en} {get_report_type_display(request.report_type, 'en')}"

    output = ReportOutput(
        title=title_zh,
        title_en=title_en,
        report_type=request.report_type,
        district=request.district,
        district_en=request.district_en,
        generated_at=now,
        document_count=document_count,
        filename=f"{request.district_en}_{request.report_type}_report_{now.strftime('%Y%m%d_%H%M')}.pdf",
    )

    try:
        # Create PDF
        logo_path = ASSETS_DIR / "c21_logo.png"
        pdf = PropertyReportPDF(title_zh, title_en, logo_path if logo_path.exists() else None)
        pdf.add_page()

        if isinstance(statistics, RentStatistics):
            _render_rent_report(pdf, statistics, images, document_count)
            output.data = {
                "count": statistics.count,
                "total_sqft": statistics.total_sqft,
                "avg_rent_sqft": statistics.avg_rent_sqft,
                "min_rent_sqft": statistics.min_rent_sqft,
                "max_rent_sqft": statistics.max_rent_sqft,
                "by_building": statistics.by_building,
            }
        elif isinstance(statistics, AvailabilityStatistics):
            _render_availability_report(pdf, statistics, images, document_count)
            output.data = {
                "count": statistics.count,
                "total_sqft": statistics.total_sqft,
                "size_range": statistics.size_range,
                "rent_range": statistics.rent_range,
            }

        # Get PDF bytes
        output.pdf_bytes = pdf.output()

        # Generate summary markdown
        output.summary_markdown = _generate_summary_markdown(request, statistics, document_count)

    except Exception as e:
        output.error = f"PDF generation failed: {str(e)}"
        output.summary_markdown = _generate_markdown_fallback(request, statistics, document_count)

    return output


def _download_image_to_temp(url: str, timeout: int = 10) -> Optional[str]:
    """Download image from URL to temp file.

    Returns path to temp file, or None if download fails.
    """
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        if response.status_code == 200 and response.headers.get("content-type", "").startswith("image"):
            # Determine extension from content-type
            content_type = response.headers.get("content-type", "image/jpeg")
            ext = ".jpg" if "jpeg" in content_type else ".png" if "png" in content_type else ".jpg"

            # Write to temp file
            temp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
            temp_file.write(response.content)
            temp_file.close()
            return temp_file.name
    except Exception as e:
        print(f"Failed to download image {url}: {e}")
    return None


def _render_image_grid(pdf: PropertyReportPDF, images: list[dict], max_images: int = 9):
    """Render property images in a grid layout.

    Args:
        pdf: PDF instance
        images: List of image dicts with 'url' and optionally 'building' keys
        max_images: Maximum number of images to display (default: 9 for 3x3 grid)
    """
    if not images:
        return

    # Filter to valid URLs and limit
    valid_images = [img for img in images if img.get("url")][:max_images]
    if not valid_images:
        return

    pdf.section_title("Property Images")

    # Grid configuration: 3 columns
    cols = 3
    img_width = 58  # Width per image
    img_height = 40  # Height per image
    margin_x = 10
    spacing = 5

    downloaded_files = []
    try:
        for i, img in enumerate(valid_images):
            # Calculate position
            col = i % cols
            row = i // cols
            x = margin_x + col * (img_width + spacing)
            y = pdf.get_y() + row * (img_height + 15)

            # Check if we need a new page
            if y + img_height + 15 > 270:
                pdf.add_page()
                y = pdf.get_y()

            # Download image
            temp_path = _download_image_to_temp(img["url"])
            if temp_path:
                downloaded_files.append(temp_path)
                try:
                    pdf.image(temp_path, x, y, img_width, img_height)

                    # Add building name label below image
                    building = img.get("building", "")
                    if building:
                        pdf.set_xy(x, y + img_height + 1)
                        if pdf.has_chinese_font:
                            pdf.set_font("Chinese", "", 6)
                        else:
                            pdf.set_font("Helvetica", "", 6)
                        pdf.set_text_color(113, 128, 150)
                        pdf.cell(img_width, 4, _safe_text(building, 25), align="C")
                except Exception as e:
                    print(f"Failed to embed image: {e}")

        # Move Y position after grid
        total_rows = (len(valid_images) + cols - 1) // cols
        pdf.set_y(pdf.get_y() + total_rows * (img_height + 15) + 10)

    finally:
        # Clean up temp files
        for f in downloaded_files:
            try:
                os.unlink(f)
            except:
                pass


def _render_rent_report(pdf: PropertyReportPDF, stats: RentStatistics, images: list[dict], doc_count: int):
    """Render rent analysis report content."""
    # Section: Market Overview
    pdf.section_title("Market Overview")

    # Stats cards
    y = pdf.get_y()
    pdf.stat_card("Properties", str(stats.count), 10, y)
    pdf.stat_card("Avg $/sqft", f"${stats.avg_rent_sqft:.1f}" if stats.avg_rent_sqft else "N/A", 58, y)
    pdf.stat_card("Min $/sqft", f"${stats.min_rent_sqft:.1f}" if stats.min_rent_sqft else "N/A", 106, y)
    pdf.stat_card("Max $/sqft", f"${stats.max_rent_sqft:.1f}" if stats.max_rent_sqft else "N/A", 154, y)

    pdf.set_y(y + 28)

    # Data source note
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(113, 128, 150)
    pdf.cell(0, 5, f"Data Source: {doc_count} processed documents | Avg Size: {_format_number(stats.avg_size_sqft)} sqft", ln=True)
    pdf.ln(5)

    # Section: Building Analysis
    if stats.by_building:
        pdf.section_title("Building Analysis")
        headers = ["Building", "Units", "Avg $/sqft", "Min", "Max"]
        rows = []
        for building, data in list(stats.by_building.items())[:10]:
            rows.append([
                _safe_text(building, 20),
                str(data["count"]),
                f"${data['avg_rent_sqft']:.1f}",
                f"${data['min_rent_sqft']:.1f}",
                f"${data['max_rent_sqft']:.1f}",
            ])
        if rows:
            pdf.data_table(headers, rows, [60, 25, 35, 35, 35])
            pdf.ln(5)

    # Section: Property Listings
    if stats.properties:
        pdf.section_title("Property Listings")
        headers = ["Building", "Floor/Unit", "Size", "Rent", "$/sqft", "Contact"]
        rows = []
        for prop in stats.properties[:15]:
            rows.append([
                _safe_text(prop.get("building_name", ""), 18),
                _safe_text(prop.get("floor_unit", ""), 10),
                _format_number(prop.get("size_sqft")),
                _format_currency(prop.get("rent_monthly")),
                f"${prop.get('rent_sqft', 0):.1f}",
                _safe_text(prop.get("contact_name", ""), 12),
            ])
        pdf.data_table(headers, rows, [45, 25, 25, 30, 25, 40])

        if len(stats.properties) > 15:
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(113, 128, 150)
            pdf.cell(0, 5, f"Showing 15 of {len(stats.properties)} properties", align="C")

    # Section: Property Images (if available)
    if images:
        pdf.ln(10)
        _render_image_grid(pdf, images)


def _render_availability_report(pdf: PropertyReportPDF, stats: AvailabilityStatistics, images: list[dict], doc_count: int):
    """Render availability report content."""
    # Section: Availability Overview
    pdf.section_title("Availability Overview")

    # Stats cards
    y = pdf.get_y()
    pdf.stat_card("Available Units", str(stats.count), 10, y)
    pdf.stat_card("Total sqft", _format_number(stats.total_sqft), 58, y)
    pdf.stat_card("Min Size", _format_number(stats.size_range[0]) if stats.size_range[0] else "N/A", 106, y)
    pdf.stat_card("Max Size", _format_number(stats.size_range[1]) if stats.size_range[1] else "N/A", 154, y)

    pdf.set_y(y + 28)

    # Rent range note
    if stats.rent_range[0] and stats.rent_range[1]:
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(113, 128, 150)
        pdf.cell(0, 5, f"Rent Range: {_format_currency(stats.rent_range[0])} - {_format_currency(stats.rent_range[1])} /month | Data Source: {doc_count} documents", ln=True)
    pdf.ln(5)

    # Section: By Size Category
    if stats.by_size_bucket:
        pdf.section_title("By Size Category")
        headers = ["Size Category", "Units", "Avg Rent"]
        rows = []
        for bucket, data in stats.by_size_bucket.items():
            rows.append([
                bucket,
                str(data["count"]),
                _format_currency(data.get("avg_rent")) if data.get("avg_rent") else "N/A",
            ])
        pdf.data_table(headers, rows, [80, 50, 60])
        pdf.ln(5)

    # Section: Available Units
    if stats.properties:
        pdf.section_title("Available Units")
        headers = ["Building", "Address", "Floor/Unit", "Size", "Rent", "Contact"]
        rows = []
        for prop in stats.properties[:20]:
            rows.append([
                _safe_text(prop.get("building_name", ""), 15),
                _safe_text(prop.get("address", ""), 20),
                _safe_text(prop.get("floor_unit", ""), 8),
                _format_number(prop.get("size_sqft")),
                _format_currency(prop.get("rent_monthly")) if prop.get("rent_monthly") else "TBD",
                _safe_text(prop.get("contact_name", ""), 10),
            ])
        if rows:
            pdf.data_table(headers, rows, [35, 45, 20, 25, 30, 35])

    # Section: Property Images (if available)
    if images:
        pdf.ln(10)
        _render_image_grid(pdf, images)


def _generate_summary_markdown(
    request: ReportRequest,
    statistics: RentStatistics | AvailabilityStatistics,
    document_count: int
) -> str:
    """Generate summary markdown for chat display."""
    if isinstance(statistics, RentStatistics):
        return f"""📊 **{request.district}區租金分析報告** 已生成

**摘要 Summary:**
- 物業數量 Properties: **{statistics.count}**
- 平均呎租 Avg Rent: **${statistics.avg_rent_sqft}/sqft**
- 呎租範圍 Range: ${statistics.min_rent_sqft} - ${statistics.max_rent_sqft}/sqft
- 數據來源 Sources: {document_count} 份文件

📄 點擊下載完整 PDF 報告"""

    elif isinstance(statistics, AvailabilityStatistics):
        return f"""🏢 **{request.district}區空置單位報告** 已生成

**摘要 Summary:**
- 空置單位 Units: **{statistics.count}**
- 總面積 Total: **{statistics.total_sqft:,.0f} sqft**
- 面積範圍 Size: {statistics.size_range[0]:,.0f} - {statistics.size_range[1]:,.0f} sqft
- 數據來源 Sources: {document_count} 份文件

📄 點擊下載完整 PDF 報告"""

    return f"報告已生成，共 {document_count} 份文件"


def _generate_markdown_fallback(
    request: ReportRequest,
    statistics: RentStatistics | AvailabilityStatistics,
    document_count: int
) -> str:
    """Generate markdown report as fallback."""
    lines = [
        f"## 📊 {request.district}區{get_report_type_display(request.report_type, 'zh')}",
        f"### {request.district_en} {get_report_type_display(request.report_type, 'en')}",
        "",
        f"**生成日期:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**數據來源:** {document_count} 份文件",
        "",
    ]

    if isinstance(statistics, RentStatistics) and statistics.count > 0:
        lines.extend([
            "### 市場概覽 Market Overview",
            "",
            f"| 指標 | 數值 |",
            f"|------|------|",
            f"| 物業數量 Properties | {statistics.count} |",
            f"| 平均呎租 Avg Rent | ${statistics.avg_rent_sqft}/sqft |",
            f"| 最低呎租 Min Rent | ${statistics.min_rent_sqft}/sqft |",
            f"| 最高呎租 Max Rent | ${statistics.max_rent_sqft}/sqft |",
            f"| 平均面積 Avg Size | {statistics.avg_size_sqft:,.0f} sqft |",
            "",
        ])

        if statistics.properties:
            lines.extend([
                "### 物業列表 Property Listings",
                "",
                "| 大廈 Building | 面積 Size | 月租 Rent | 呎租 $/sqft |",
                "|--------------|----------|----------|------------|",
            ])
            for prop in statistics.properties[:10]:
                lines.append(
                    f"| {prop['building_name']} | {prop['size_sqft']:,.0f} | "
                    f"${prop['rent_monthly']:,.0f} | ${prop['rent_sqft']:.2f} |"
                )

    return "\n".join(lines)


@traceable(name="upload_pdf_to_blob", run_type="tool")
def upload_pdf_to_blob(output: ReportOutput) -> Optional[str]:
    """Upload generated PDF to Azure Blob Storage.

    Args:
        output: ReportOutput with pdf_bytes

    Returns:
        Public URL of uploaded PDF, or None if upload failed
    """
    if not output.pdf_bytes:
        return None

    try:
        from src.utils.blob_storage import get_blob_service_client

        client = get_blob_service_client()
        if not client:
            return None

        container_name = os.environ.get("AZURE_BLOB_REPORTS_CONTAINER", "reports")

        # Get container client
        container_client = client.get_container_client(container_name)
        if not container_client.exists():
            container_client.create_container(public_access="blob")

        # Upload PDF
        blob_name = f"{datetime.now().strftime('%Y/%m')}/{output.filename}"
        blob_client = container_client.get_blob_client(blob_name)

        from azure.storage.blob import ContentSettings
        blob_client.upload_blob(
            output.pdf_bytes,
            overwrite=True,
            content_settings=ContentSettings(content_type="application/pdf")
        )

        output.pdf_url = blob_client.url
        return output.pdf_url

    except Exception as e:
        print(f"Failed to upload PDF: {e}")
        return None
