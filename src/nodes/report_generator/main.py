"""Main orchestrator for report generation.

This module provides the entry point for generating reports from chatbot queries.
"""

from typing import Optional
from dataclasses import dataclass

from langsmith import traceable

from .router import detect_report_intent, parse_report_request, ReportRequest
from .validator import validate_request, ValidationResult
from .aggregator import aggregate_for_rent_report, aggregate_for_availability_report
from .statistics import compute_rent_statistics, compute_availability_statistics
from .pdf_generator import generate_pdf_report, upload_pdf_to_blob, ReportOutput


@dataclass
class ReportResponse:
    """Response from report generation attempt."""
    is_report_request: bool = False
    needs_more_info: bool = False
    prompt_message: Optional[str] = None  # Message to ask user for more info
    report: Optional[ReportOutput] = None
    error: Optional[str] = None


@traceable(name="handle_report_request", run_type="chain")
def handle_report_request(query: str) -> ReportResponse:
    """Handle a potential report request from the chatbot.

    This is the main entry point called by the chatbot when routing to reports.

    Args:
        query: User's natural language query

    Returns:
        ReportResponse indicating:
        - Not a report request → is_report_request=False
        - Needs more info → needs_more_info=True, prompt_message set
        - Success → report set with PDF
        - Error → error message set
    """
    response = ReportResponse()

    # 1. Check if this is a report request
    if not detect_report_intent(query):
        response.is_report_request = False
        return response

    response.is_report_request = True

    # 2. Parse the request
    request = parse_report_request(query)

    # 3. Validate parameters
    validation = validate_request(request)
    if not validation.is_valid:
        response.needs_more_info = True
        response.prompt_message = validation.prompt_message
        return response

    # 4. Generate report based on type
    try:
        if request.report_type == "rent":
            response.report = _generate_rent_report(request)
        elif request.report_type == "availability":
            response.report = _generate_availability_report(request)
        else:
            # Default to rent analysis for now
            response.report = _generate_rent_report(request)

        # 5. Upload PDF to blob storage
        if response.report and response.report.pdf_bytes:
            upload_pdf_to_blob(response.report)

    except Exception as e:
        response.error = f"報告生成失敗 Report generation failed: {str(e)}"

    return response


@traceable(name="generate_rent_report", run_type="chain")
def _generate_rent_report(request: ReportRequest) -> ReportOutput:
    """Generate rent analysis report."""
    # Aggregate documents
    documents, images = aggregate_for_rent_report(request)

    if not documents:
        output = ReportOutput(
            title=f"{request.district}區租金分析報告",
            title_en=f"{request.district_en} Rent Analysis Report",
            report_type="rent",
            district=request.district,
            district_en=request.district_en,
            generated_at=__import__("datetime").datetime.now(),
            document_count=0,
            error="未找到相關物業資料 No matching properties found"
        )
        output.summary_markdown = f"⚠️ 未找到 {request.district} 區的物業資料。請確認地區名稱或嘗試其他地區。"
        return output

    # Compute statistics
    stats = compute_rent_statistics(documents)

    # Generate PDF
    return generate_pdf_report(
        request=request,
        statistics=stats,
        images=images,
        document_count=len(documents)
    )


@traceable(name="generate_availability_report", run_type="chain")
def _generate_availability_report(request: ReportRequest) -> ReportOutput:
    """Generate availability report."""
    # Aggregate documents
    documents, images = aggregate_for_availability_report(request)

    if not documents:
        output = ReportOutput(
            title=f"{request.district}區空置單位報告",
            title_en=f"{request.district_en} Availability Report",
            report_type="availability",
            district=request.district,
            district_en=request.district_en,
            generated_at=__import__("datetime").datetime.now(),
            document_count=0,
            error="未找到相關物業資料 No matching properties found"
        )
        output.summary_markdown = f"⚠️ 未找到 {request.district} 區的空置物業資料。請確認地區名稱或嘗試其他地區。"
        return output

    # Compute statistics
    stats = compute_availability_statistics(documents)

    # Generate PDF
    return generate_pdf_report(
        request=request,
        statistics=stats,
        images=images,
        document_count=len(documents)
    )


# Export for chatbot integration
__all__ = ["handle_report_request", "ReportResponse", "detect_report_intent"]
