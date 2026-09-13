"""Immediate Odoo listing -> BAS properties-index sync (demo requirement, 2026-09-12).

Previously this pipeline only wrote to Odoo; a *separate* standalone project
(odoo-bas-sync) picked up anything with x_c21_published=False on a daily 18:00 UTC
timer and embedded/upserted it into BAS's properties-index. For demo purposes the
plan changed: write to both immediately on every document, while KEEPING the daily
job running unchanged as a reconciliation pass for listings edited directly in Odoo
(which this pipeline never sees).

Design that makes the two paths compose for free, no new reconciliation logic:
x_c21_published is only flipped to True here on a *successful* embed+upsert. Any
failure (network blip, rate limit, etc.) leaves it False, and the existing daily
job's query (`x_c21_published=False`) already picks those up on its own next run.

mapping logic (build_content/map_listing/DISTRICT_LABELS) is ported verbatim from
odoo-bas-sync/mapping.py (a separate repo/deployment, no code-sharing between the
two) — it's pure Python with no I/O, safe to duplicate. The embed/upsert credentials
are NOT ported the same way: odoo-bas-sync auths via managed identity against BAS's
own OpenAI resource (c21net-bas-oai-fc-ea-prod), which this App Service has no
identity/RBAC for. Instead this reuses credentials this repo already has:
AZURE_OPENAI_* (this repo's own OpenAI resource, same text-embedding-3-large model/
3072 dims) for embedding, and AZURE_SEARCH_API_KEY (confirmed to be the actual admin
key for c21net-bas-srch-ea-prod, the same service properties-index lives on) for the
Search write — no new Azure resources or bas-stacks RBAC grants needed.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

ODOO_MODEL = "x_c21_listing"
ODOO_DB = "c21net"

BAS_SEARCH_INDEX = "properties-index"

FIELDS = [
    "id",
    "x_name",
    "x_c21_address",
    "x_c21_district",
    "x_c21_property_type",
    "x_c21_rent_net",
    "x_c21_size_sqft",
    "x_c21_contact_name",
    "x_c21_contact_phone",
    "x_c21_floor_unit",
    "x_c21_date_received",
    "x_c21_ocr_text",
    "x_c21_doc_url",
]

# Odoo stores district as a snake_case selection key (e.g. "kwun_tong"). BAS expects
# a readable English label. Kept in sync with odoo-bas-sync/mapping.py by hand (the
# two repos don't share code) — if that list grows, mirror the change here too.
DISTRICT_LABELS: dict[str, str] = {
    "kwun_tong": "Kwun Tong",
    "kwai_fong": "Kwai Fong",
    "kwai_chung": "Kwai Chung",
    "tsuen_wan": "Tsuen Wan",
    "mong_kok": "Mong Kok",
    "tsim_sha_tsui": "Tsim Sha Tsui",
    "causeway_bay": "Causeway Bay",
    "wan_chai": "Wan Chai",
    "central": "Central",
    "sheung_wan": "Sheung Wan",
    "cheung_sha_wan": "Cheung Sha Wan",
    "kowloon_bay": "Kowloon Bay",
    "san_po_kong": "San Po Kong",
}


def _iso_date(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def build_content(record: dict) -> str:
    """Real OCR text when available, else a thin structured fallback."""
    ocr_text = (record.get("x_c21_ocr_text") or "").strip()
    if ocr_text:
        return ocr_text
    parts = [record.get("x_name"), record.get("x_c21_address"), record.get("x_c21_floor_unit")]
    return " / ".join(p for p in parts if p)


def map_listing(record: dict) -> dict:
    """Build the BAS properties-index document for one Odoo x_c21_listing record.

    Does not include contentVector — the caller embeds build_content() separately.
    """
    record_id = record["id"]
    return {
        "id": f"odoo-listing-{record_id}",
        "address": record.get("x_c21_address") or record.get("x_name") or "",
        "district": DISTRICT_LABELS.get(record.get("x_c21_district") or "", ""),
        "propertyType": record.get("x_c21_property_type") or "",
        "price": record.get("x_c21_rent_net") or None,
        "area_sqft": record.get("x_c21_size_sqft") or None,
        "agentName": record.get("x_c21_contact_name") or "",
        "listingDate": _iso_date(record.get("x_c21_date_received")),
        "sourceWebUrl": record.get("x_c21_doc_url") or "",
        "sourceBlob": f"odoo-listing-{record_id}",
        "docType": "property_listing",
        "transactionType": "rent",
        "content": build_content(record),
    }


_embed_client = None
_search_client = None


def _get_embed_client():
    global _embed_client
    if _embed_client is None:
        from openai import AzureOpenAI
        _embed_client = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_KEY"],
            api_version="2024-06-01",
        )
    return _embed_client


def _get_search_client():
    global _search_client
    if _search_client is None:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient
        _search_client = SearchClient(
            endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
            index_name=BAS_SEARCH_INDEX,
            credential=AzureKeyCredential(os.environ["AZURE_SEARCH_API_KEY"]),
        )
    return _search_client


def embed(text: str) -> list[float]:
    deployment = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large")
    text = text[:8000]
    response = _get_embed_client().embeddings.create(input=text, model=deployment)
    return response.data[0].embedding


def upsert(doc: dict) -> None:
    result = _get_search_client().merge_or_upload_documents([doc])
    if not result[0].succeeded:
        raise RuntimeError(f"Search upsert failed for {doc['id']}: {result[0].error_message}")


def sync_listings_to_bas(models: Any, uid: int, api_key: str, listing_ids: list[int]) -> list[int]:
    """Embed + upsert each listing into properties-index. Returns the subset of
    listing_ids that succeeded — callers should only flip x_c21_published=True for
    those, leaving failures False so the daily reconciliation job retries them."""
    if not listing_ids:
        return []
    try:
        records = models.execute_kw(
            ODOO_DB, uid, api_key, ODOO_MODEL, "read", [listing_ids], {"fields": FIELDS},
        )
    except Exception as e:
        logger.warning("bas_index_sync: failed to read listings %s for BAS sync: %s", listing_ids, e)
        return []

    succeeded: list[int] = []
    for record in records:
        record_id = record["id"]
        try:
            doc = map_listing(record)
            doc["contentVector"] = embed(build_content(record))
            upsert(doc)
            succeeded.append(record_id)
        except Exception as e:
            logger.warning("bas_index_sync: failed to sync listing %s to BAS: %s", record_id, e)
    return succeeded
