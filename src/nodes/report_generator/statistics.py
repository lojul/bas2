"""Compute statistics from aggregated documents.

All statistics are computed in Python from real data.
NO LLM is used for generating numbers - this prevents hallucination.
"""

import statistics as stats
from typing import Optional
from dataclasses import dataclass, field
from collections import defaultdict

from langsmith import traceable


@dataclass
class RentStatistics:
    """Statistics for rent analysis report."""
    count: int = 0
    total_sqft: float = 0
    avg_rent_sqft: Optional[float] = None
    min_rent_sqft: Optional[float] = None
    max_rent_sqft: Optional[float] = None
    avg_size_sqft: Optional[float] = None
    by_building: dict = field(default_factory=dict)
    by_property_type: dict = field(default_factory=dict)
    properties: list = field(default_factory=list)


@dataclass
class AvailabilityStatistics:
    """Statistics for availability report."""
    count: int = 0
    total_sqft: float = 0
    size_range: tuple = (0, 0)
    rent_range: tuple = (0, 0)
    by_size_bucket: dict = field(default_factory=dict)
    properties: list = field(default_factory=list)


def _parse_number(value) -> Optional[float]:
    """Parse a number from various formats."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # Remove common formatting
        cleaned = value.replace(",", "").replace("$", "").replace("HK", "").strip()
        # Extract numbers
        import re
        match = re.search(r"[\d.]+", cleaned)
        if match:
            try:
                return float(match.group())
            except ValueError:
                pass
    return None


def _get_size_bucket(size: float) -> str:
    """Categorize size into buckets."""
    if size < 500:
        return "<500 sqft"
    elif size < 1000:
        return "500-1000 sqft"
    elif size < 2000:
        return "1000-2000 sqft"
    elif size < 5000:
        return "2000-5000 sqft"
    else:
        return ">5000 sqft"


# Document types that represent single listings (with direct rent/size)
SINGLE_LISTING_TYPES = {"listing", "vacancy listing", "particular property"}
# Document types that represent multiple listings (with units array)
MULTI_LISTING_TYPES = {"listing_list"}


@traceable(name="compute_rent_statistics", run_type="chain")
def compute_rent_statistics(documents: list[dict]) -> RentStatistics:
    """Compute rent statistics from documents.

    Args:
        documents: List of documents with extracted_data parsed

    Returns:
        RentStatistics with computed values
    """
    result = RentStatistics()
    rent_sqft_values = []
    size_values = []
    building_data = defaultdict(list)
    type_data = defaultdict(list)

    for doc in documents:
        extracted = doc.get("extracted_data") or {}
        doc_type = (doc.get("document_type") or "").lower()

        if doc_type in SINGLE_LISTING_TYPES:
            # Single listing
            rent = _parse_number(extracted.get("rent_monthly") or extracted.get("rent"))
            size = _parse_number(extracted.get("size_sqft") or extracted.get("size"))

            if rent and size and size > 0:
                rent_sqft = rent / size
                rent_sqft_values.append(rent_sqft)
                size_values.append(size)

                building = extracted.get("building_name") or "Unknown"
                prop_type = extracted.get("property_type") or "Unknown"

                building_data[building].append(rent_sqft)
                type_data[prop_type].append(rent_sqft)

                # Handle contact safely (might be None)
                contact = extracted.get("contact") or {}
                image_urls = doc.get("image_urls") or []

                result.properties.append({
                    "building_name": building,
                    "address": extracted.get("address") or "",
                    "size_sqft": size,
                    "rent_monthly": rent,
                    "rent_sqft": round(rent_sqft, 2),
                    "floor_unit": extracted.get("floor_unit") or "",
                    "property_type": prop_type,
                    "contact_name": contact.get("name") or "",
                    "contact_phone": contact.get("phone") or "",
                    "image_url": image_urls[0] if image_urls else None,
                })

        elif doc_type in MULTI_LISTING_TYPES:
            # Multiple listings - handle both old and new data formats
            # Old format: extracted_data.units[] (direct)
            # New format: extracted_data.items[].units[] (nested per building)

            direct_units = extracted.get("units") or []
            items = extracted.get("items") or []

            # Collect all units from both formats
            all_units = []
            building_map = {}  # unit -> building_name

            # Old format: direct units array
            building = extracted.get("building_name") or "Unknown"
            for unit in direct_units:
                all_units.append(unit)
                building_map[id(unit)] = building

            # New format: items array with nested units
            for item in items:
                item_building = item.get("building_name") or "Unknown"
                item_units = item.get("units") or []
                for unit in item_units:
                    all_units.append(unit)
                    building_map[id(unit)] = item_building

            for unit in all_units:
                building = building_map.get(id(unit), "Unknown")
                rent = _parse_number(unit.get("rent"))
                size = _parse_number(unit.get("size"))

                if rent and size and size > 0:
                    rent_sqft = rent / size
                    rent_sqft_values.append(rent_sqft)
                    size_values.append(size)

                    prop_type = unit.get("property_type") or extracted.get("property_type") or "Unknown"

                    building_data[building].append(rent_sqft)
                    type_data[prop_type].append(rent_sqft)

                    # Handle contact and images safely
                    contact = extracted.get("contact") or {}
                    image_urls = doc.get("image_urls") or []
                    floor = unit.get("floor") or ""
                    unit_num = unit.get("unit") or ""

                    result.properties.append({
                        "building_name": building,
                        "address": extracted.get("address") or "",
                        "size_sqft": size,
                        "rent_monthly": rent,
                        "rent_sqft": round(rent_sqft, 2),
                        "floor_unit": f"{floor} {unit_num}".strip(),
                        "property_type": prop_type,
                        "contact_name": contact.get("name") or "",
                        "contact_phone": contact.get("phone") or "",
                        "image_url": image_urls[0] if image_urls else None,
                    })

    # Compute aggregates
    if rent_sqft_values:
        result.count = len(rent_sqft_values)
        result.total_sqft = sum(size_values)
        result.avg_rent_sqft = round(stats.mean(rent_sqft_values), 2)
        result.min_rent_sqft = round(min(rent_sqft_values), 2)
        result.max_rent_sqft = round(max(rent_sqft_values), 2)
        result.avg_size_sqft = round(stats.mean(size_values), 0)

        # By building
        for building, values in building_data.items():
            result.by_building[building] = {
                "count": len(values),
                "avg_rent_sqft": round(stats.mean(values), 2),
                "min_rent_sqft": round(min(values), 2),
                "max_rent_sqft": round(max(values), 2),
            }

        # By property type
        for prop_type, values in type_data.items():
            result.by_property_type[prop_type] = {
                "count": len(values),
                "avg_rent_sqft": round(stats.mean(values), 2),
            }

    # Sort properties by rent_sqft
    result.properties.sort(key=lambda x: x.get("rent_sqft", 0), reverse=True)

    return result


@traceable(name="compute_availability_statistics", run_type="chain")
def compute_availability_statistics(documents: list[dict]) -> AvailabilityStatistics:
    """Compute availability statistics from documents.

    Args:
        documents: List of documents with extracted_data parsed

    Returns:
        AvailabilityStatistics with computed values
    """
    result = AvailabilityStatistics()
    sizes = []
    rents = []
    bucket_data = defaultdict(list)

    for doc in documents:
        extracted = doc.get("extracted_data") or {}
        doc_type = (doc.get("document_type") or "").lower()

        if doc_type in SINGLE_LISTING_TYPES:
            size = _parse_number(extracted.get("size_sqft") or extracted.get("size"))
            rent = _parse_number(extracted.get("rent_monthly") or extracted.get("rent"))

            if size:
                sizes.append(size)
                bucket = _get_size_bucket(size)
                bucket_data[bucket].append({"size": size, "rent": rent})

                if rent:
                    rents.append(rent)

                # Handle None values safely
                contact = extracted.get("contact") or {}
                image_urls = doc.get("image_urls") or []

                result.properties.append({
                    "building_name": extracted.get("building_name") or "Unknown",
                    "address": extracted.get("address") or "",
                    "size_sqft": size,
                    "rent_monthly": rent,
                    "floor_unit": extracted.get("floor_unit") or "",
                    "contact_name": contact.get("name") or "",
                    "contact_phone": contact.get("phone") or "",
                    "image_url": image_urls[0] if image_urls else None,
                })

        elif doc_type in MULTI_LISTING_TYPES:
            # Handle both old and new data formats
            direct_units = extracted.get("units") or []
            items = extracted.get("items") or []

            # Collect all units from both formats
            all_units = []
            building_map = {}

            building = extracted.get("building_name") or "Unknown"
            for unit in direct_units:
                all_units.append(unit)
                building_map[id(unit)] = building

            for item in items:
                item_building = item.get("building_name") or "Unknown"
                for unit in item.get("units") or []:
                    all_units.append(unit)
                    building_map[id(unit)] = item_building

            for unit in all_units:
                building = building_map.get(id(unit), "Unknown")
                size = _parse_number(unit.get("size"))
                rent = _parse_number(unit.get("rent"))

                if size:
                    sizes.append(size)
                    bucket = _get_size_bucket(size)
                    bucket_data[bucket].append({"size": size, "rent": rent})

                    if rent:
                        rents.append(rent)

                    # Handle None values safely
                    contact = extracted.get("contact") or {}
                    image_urls = doc.get("image_urls") or []
                    floor = unit.get("floor") or ""
                    unit_num = unit.get("unit") or ""

                    result.properties.append({
                        "building_name": building,
                        "address": extracted.get("address") or "",
                        "size_sqft": size,
                        "rent_monthly": rent,
                        "floor_unit": f"{floor} {unit_num}".strip(),
                        "contact_name": contact.get("name") or "",
                        "contact_phone": contact.get("phone") or "",
                        "image_url": image_urls[0] if image_urls else None,
                    })

    # Compute aggregates
    if sizes:
        result.count = len(sizes)
        result.total_sqft = sum(sizes)
        result.size_range = (min(sizes), max(sizes))

    if rents:
        result.rent_range = (min(rents), max(rents))

    # By size bucket
    for bucket, items in bucket_data.items():
        avg_rent = None
        rents_in_bucket = [x["rent"] for x in items if x["rent"]]
        if rents_in_bucket:
            avg_rent = round(stats.mean(rents_in_bucket), 0)

        result.by_size_bucket[bucket] = {
            "count": len(items),
            "avg_rent": avg_rent,
        }

    # Sort properties by size
    result.properties.sort(key=lambda x: x.get("size_sqft", 0), reverse=True)

    return result
