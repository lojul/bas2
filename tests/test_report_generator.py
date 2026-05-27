"""Tests for report generator module."""

import pytest
from unittest.mock import patch, MagicMock

from src.nodes.report_generator.router import (
    detect_report_intent,
    parse_report_request,
    ReportRequest,
)
from src.nodes.report_generator.validator import validate_request
from src.nodes.report_generator.statistics import (
    compute_rent_statistics,
    compute_availability_statistics,
    RentStatistics,
)


class TestReportRouter:
    """Test report intent detection and parsing."""

    def test_detect_report_intent_chinese(self):
        """Should detect Chinese report requests."""
        assert detect_report_intent("幫我生成中環租金報告") is True
        assert detect_report_intent("製作觀塘區空置單位報告") is True
        assert detect_report_intent("整理尖沙咀市場概覽") is True

    def test_detect_report_intent_english(self):
        """Should detect English report requests."""
        assert detect_report_intent("Generate a rent report for Central") is True
        assert detect_report_intent("Create availability report for Kwun Tong") is True

    def test_detect_report_intent_negative(self):
        """Should not detect non-report queries."""
        assert detect_report_intent("中環有什麼寫字樓出租") is False
        assert detect_report_intent("What offices are available in Central?") is False
        assert detect_report_intent("市場趨勢如何") is False

    def test_parse_report_request_chinese(self):
        """Should parse Chinese report request."""
        request = parse_report_request("幫我生成中環租金報告")
        assert request.report_type == "rent"
        assert request.district == "中環"
        assert request.district_en == "Central"

    def test_parse_report_request_english(self):
        """Should parse English report request."""
        request = parse_report_request("Generate rent report for Kwun Tong")
        assert request.report_type == "rent"
        assert request.district == "觀塘"
        assert request.district_en == "Kwun Tong"

    def test_parse_report_request_availability(self):
        """Should detect availability report type."""
        request = parse_report_request("生成九龍灣空置單位報告")
        assert request.report_type == "availability"
        assert request.district == "九龍灣"

    def test_parse_report_request_no_district(self):
        """Should handle missing district."""
        request = parse_report_request("Generate a rent report")
        assert request.report_type == "rent"
        assert request.district is None


class TestReportValidator:
    """Test report request validation."""

    def test_validate_complete_request(self):
        """Should validate complete request."""
        request = ReportRequest(
            report_type="rent",
            district="中環",
            district_en="Central",
            raw_query="Generate rent report for Central"
        )
        result = validate_request(request)
        assert result.is_valid is True
        assert len(result.missing_params) == 0

    def test_validate_missing_district(self):
        """Should detect missing district."""
        request = ReportRequest(
            report_type="rent",
            district=None,
            raw_query="Generate rent report"
        )
        result = validate_request(request)
        assert result.is_valid is False
        assert "district" in result.missing_params
        assert result.prompt_message is not None


class TestRentStatistics:
    """Test rent statistics computation."""

    def test_compute_rent_statistics_listing(self):
        """Should compute statistics from listing documents."""
        documents = [
            {
                "document_type": "listing",
                "extracted_data": {
                    "building_name": "Test Building",
                    "rent_monthly": 50000,
                    "size_sqft": 1000,
                    "property_type": "office",
                    "contact": {"name": "Agent A", "phone": "12345678"}
                },
                "image_urls": []
            },
            {
                "document_type": "listing",
                "extracted_data": {
                    "building_name": "Test Building 2",
                    "rent_monthly": 30000,
                    "size_sqft": 500,
                    "property_type": "office",
                    "contact": {"name": "Agent B", "phone": "87654321"}
                },
                "image_urls": []
            }
        ]

        stats = compute_rent_statistics(documents)

        assert stats.count == 2
        assert stats.avg_rent_sqft == 55.0  # (50 + 60) / 2
        assert stats.min_rent_sqft == 50.0
        assert stats.max_rent_sqft == 60.0
        assert len(stats.properties) == 2

    def test_compute_rent_statistics_listing_list(self):
        """Should compute statistics from listing_list documents."""
        documents = [
            {
                "document_type": "listing_list",
                "extracted_data": {
                    "building_name": "Multi-Unit Building",
                    "address": "123 Test Street",
                    "units": [
                        {"rent": 40000, "size": 800, "floor": "10/F"},
                        {"rent": 45000, "size": 900, "floor": "11/F"},
                    ],
                    "contact": {"name": "Agent C"}
                },
                "image_urls": []
            }
        ]

        stats = compute_rent_statistics(documents)

        assert stats.count == 2
        assert len(stats.properties) == 2

    def test_compute_rent_statistics_empty(self):
        """Should handle empty documents."""
        stats = compute_rent_statistics([])
        assert stats.count == 0
        assert stats.avg_rent_sqft is None


class TestAvailabilityStatistics:
    """Test availability statistics computation."""

    def test_compute_availability_statistics(self):
        """Should compute availability statistics."""
        documents = [
            {
                "document_type": "listing",
                "extracted_data": {
                    "building_name": "Building A",
                    "size_sqft": 1500,
                    "rent_monthly": 75000,
                },
                "image_urls": []
            },
            {
                "document_type": "listing",
                "extracted_data": {
                    "building_name": "Building B",
                    "size_sqft": 800,
                    "rent_monthly": 32000,
                },
                "image_urls": []
            }
        ]

        stats = compute_availability_statistics(documents)

        assert stats.count == 2
        assert stats.total_sqft == 2300
        assert stats.size_range == (800, 1500)
        assert stats.rent_range == (32000, 75000)


class TestIntegration:
    """Integration tests for report generation."""

    @patch("src.nodes.report_generator.aggregator.httpx.Client")
    def test_handle_report_request_needs_district(self, mock_client):
        """Should prompt for district when missing."""
        from src.nodes.report_generator.main import handle_report_request

        response = handle_report_request("Generate a rent report")

        assert response.is_report_request is True
        assert response.needs_more_info is True
        assert response.prompt_message is not None

    def test_handle_report_request_not_report(self):
        """Should detect non-report queries."""
        from src.nodes.report_generator.main import handle_report_request

        response = handle_report_request("What offices are in Central?")

        assert response.is_report_request is False
