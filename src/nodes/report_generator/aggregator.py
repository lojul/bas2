"""Aggregate documents from Azure AI Search for reports."""

import os
import json
from typing import Optional

import httpx
from langsmith import traceable

from .router import ReportRequest, DISTRICTS


@traceable(name="aggregate_documents", run_type="retriever")
def aggregate_documents(
    request: ReportRequest,
    document_types: Optional[list[str]] = None,
    top_k: int = 100
) -> tuple[list[dict], list[dict]]:
    """Fetch all matching documents for report aggregation.

    Args:
        request: Validated report request with district/type
        document_types: Filter by document types (e.g., ["listing", "listing_list"])
        top_k: Maximum documents to fetch

    Returns:
        Tuple of (documents, images) where:
        - documents: List of document dicts with extracted_data parsed
        - images: List of image dicts {url, building, doc_id}
    """
    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    api_key = os.environ.get("AZURE_SEARCH_API_KEY")
    index_name = os.environ.get("AZURE_SEARCH_INDEX", "processed-documents")

    if not endpoint or not api_key:
        raise ValueError("Azure Search credentials not configured")

    # Build filter expression
    filters = []

    # Filter by district (search in content and extracted_data)
    # We'll use a text search instead of filter for flexibility
    search_text = ""
    if request.district:
        search_text = request.district
        # Also add English name
        if request.district_en:
            search_text += f" {request.district_en}"

    # Filter by document type
    if document_types:
        type_filter = " or ".join([f"document_type eq '{t}'" for t in document_types])
        filters.append(f"({type_filter})")

    filter_expr = " and ".join(filters) if filters else None

    # Build search request
    search_body = {
        "search": search_text or "*",
        "searchMode": "any",
        "queryType": "simple",
        "top": top_k,
        "select": "id,file_name,document_type,content,extracted_data,image_urls,processed_at",
        "orderby": "processed_at desc",
    }

    if filter_expr:
        search_body["filter"] = filter_expr

    # Execute search
    url = f"{endpoint}/indexes/{index_name}/docs/search?api-version=2024-07-01"

    with httpx.Client(timeout=30) as client:
        response = client.post(
            url,
            headers={
                "Content-Type": "application/json",
                "api-key": api_key,
            },
            json=search_body,
        )
        response.raise_for_status()
        results = response.json()

    # Process results
    documents = []
    images = []

    for doc in results.get("value", []):
        # Parse extracted_data JSON
        extracted_data = {}
        if doc.get("extracted_data"):
            try:
                extracted_data = json.loads(doc["extracted_data"])
            except json.JSONDecodeError:
                pass

        # Filter by district in extracted_data if specified
        if request.district:
            # Ensure strings (handle None values)
            doc_district = extracted_data.get("district") or ""
            doc_address = extracted_data.get("address") or ""
            doc_content = doc.get("content") or ""

            # Check if district matches
            district_match = (
                request.district in doc_district or
                request.district in doc_address or
                request.district in doc_content
            )

            # Also check English name
            if request.district_en:
                district_match = district_match or (
                    request.district_en.lower() in doc_district.lower() or
                    request.district_en.lower() in doc_address.lower() or
                    request.district_en.lower() in doc_content.lower()
                )

            if not district_match:
                continue

        # Add to documents list (handle None values explicitly)
        content = doc.get("content") or ""
        image_urls = doc.get("image_urls") or []

        doc_parsed = {
            "id": doc.get("id"),
            "file_name": doc.get("file_name") or "unknown",
            "document_type": doc.get("document_type"),
            "content": content[:500],  # Truncate for memory
            "extracted_data": extracted_data,
            "image_urls": image_urls,
            "processed_at": doc.get("processed_at"),
        }
        documents.append(doc_parsed)

        # Collect images
        building_name = extracted_data.get("building_name") or doc.get("file_name") or ""
        for url in image_urls[:3]:  # Max 3 images per doc
            images.append({
                "url": url,
                "building": building_name,
                "doc_id": doc.get("id"),
            })

    # Limit total images
    images = images[:12]  # Max 12 images in report (4x3 grid)

    return documents, images


# Document types that contain property listings
# processed-documents uses: listing, listing_list
# c21net-intelligence-v2 uses: Vacancy Listing, Particular Property
LISTING_DOC_TYPES = [
    "listing", "listing_list",  # processed-documents
    "Vacancy Listing", "Particular Property",  # c21net-intelligence-v2
]


@traceable(name="aggregate_for_rent_report", run_type="retriever")
def aggregate_for_rent_report(request: ReportRequest) -> tuple[list[dict], list[dict]]:
    """Aggregate documents specifically for rent analysis report.

    Fetches listings from all configured indexes.
    """
    return aggregate_documents(
        request=request,
        document_types=LISTING_DOC_TYPES,
        top_k=100
    )


@traceable(name="aggregate_for_availability_report", run_type="retriever")
def aggregate_for_availability_report(request: ReportRequest) -> tuple[list[dict], list[dict]]:
    """Aggregate documents for availability report.

    Fetches listings with availability info from all configured indexes.
    """
    return aggregate_documents(
        request=request,
        document_types=LISTING_DOC_TYPES,
        top_k=100
    )


@traceable(name="aggregate_for_market_report", run_type="retriever")
def aggregate_for_market_report(request: ReportRequest) -> tuple[list[dict], list[dict]]:
    """Aggregate documents for market overview report.

    Fetches listings and news articles from all configured indexes.
    """
    return aggregate_documents(
        request=request,
        document_types=LISTING_DOC_TYPES + ["news"],
        top_k=100
    )
