"""Report Generator Module for PDF reports with images.

This module generates professional PDF reports from indexed documents.
Reports are triggered via chatbot commands like:
    "Generate rent report for Central"
    "幫我生成中環租金報告"
"""

from .router import detect_report_intent, parse_report_request, ReportRequest
from .validator import validate_request, get_missing_params_prompt, ValidationResult
from .aggregator import aggregate_documents
from .statistics import compute_rent_statistics, compute_availability_statistics
from .pdf_generator import generate_pdf_report, ReportOutput
from .main import handle_report_request, ReportResponse

__all__ = [
    # Main entry point
    "handle_report_request",
    "ReportResponse",
    # Router
    "detect_report_intent",
    "parse_report_request",
    "ReportRequest",
    # Validator
    "validate_request",
    "get_missing_params_prompt",
    "ValidationResult",
    # Aggregator
    "aggregate_documents",
    # Statistics
    "compute_rent_statistics",
    "compute_availability_statistics",
    # PDF Generator
    "generate_pdf_report",
    "ReportOutput",
]
