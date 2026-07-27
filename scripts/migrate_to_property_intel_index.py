"""
Migration script: c21net-intelligence-v2 → property-intel-index

Reads all 771 docs from c21net-intelligence-v2 on c21net-bas-aisearch-ea-prod,
normalises field names and document types, re-embeds content, then upserts into
property-intel-index on c21net-bas-srch-ea-prod.

Run once:
    cd langgraph
    source .venv/bin/activate
    python scripts/migrate_to_property_intel_index.py
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()

# ── Source (old service) ──────────────────────────────────────────────────────
SRC_ENDPOINT = "https://c21net-bas-aisearch-ea-prod.search.windows.net"
SRC_KEY = "dZ7VXT8HZ5HuOdZHGpG6sIbVeiGIHdzj61Xv2i7CrUAzSeA8vNBC"  # old service key, hardcoded intentionally
SRC_INDEX = "c21net-intelligence-v2"

# ── Destination (new service) ─────────────────────────────────────────────────
DST_ENDPOINT = "https://c21net-bas-srch-ea-prod.search.windows.net"
DST_KEY = "sXe89p4Raw9zBHqk2Je4x5YuG8tRqDEijQrredyCulAzSeAQgyzI"
DST_INDEX = "property-intel-index"

# ── Azure OpenAI for re-embedding ─────────────────────────────────────────────
AOAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
AOAI_KEY = os.environ.get("AZURE_OPENAI_KEY", "")
EMBED_DEPLOYMENT = "text-embedding-3-small"
BATCH_SIZE = 50  # docs per upsert batch


def normalise_doc_type(raw: str) -> str:
    mapping = {
        "vacancy listing": "listing",
        "particular property": "listing_list",
        "name card": "contact",
        "news article": "news",
    }
    return mapping.get((raw or "").lower(), raw or "listing")


def fetch_all_docs(client: httpx.Client) -> list[dict]:
    """Fetch all documents from source index using pagination."""
    url = f"{SRC_ENDPOINT}/indexes/{SRC_INDEX}/docs/search?api-version=2024-07-01"
    headers = {"Content-Type": "application/json", "api-key": SRC_KEY}
    docs = []
    skip = 0
    page_size = 100

    while True:
        body = {
            "search": "*",
            "select": "id,title,document_type,content,content_vector,monthly_rental_hkd,floor_area_sqft,key_entities,last_updated",
            "top": page_size,
            "skip": skip,
        }
        resp = client.post(url, headers=headers, json=body, timeout=30)
        resp.raise_for_status()
        page = resp.json().get("value", [])
        docs.extend(page)
        print(f"  fetched {len(docs)} docs so far...")
        if len(page) < page_size:
            break
        skip += page_size

    return docs


def transform_doc(raw: dict) -> dict:
    """Convert c21net-intelligence-v2 doc to property-intel-index schema."""
    content = raw.get("content") or ""

    # Build extracted_data from root-level c21net fields
    extracted: dict = {}
    if raw.get("monthly_rental_hkd") is not None:
        extracted["rent_monthly"] = raw["monthly_rental_hkd"]
        extracted["rent"] = raw["monthly_rental_hkd"]
    if raw.get("floor_area_sqft") is not None:
        extracted["size_sqft"] = raw["floor_area_sqft"]
        extracted["size"] = raw["floor_area_sqft"]
    if raw.get("key_entities"):
        extracted["key_entities"] = raw["key_entities"]

    # Parse last_updated → processed_at
    last_updated = raw.get("last_updated")
    try:
        processed_at = datetime.fromisoformat(
            last_updated.replace("Z", "+00:00")
        ).isoformat() if last_updated else datetime.now(timezone.utc).isoformat()
    except Exception:
        processed_at = datetime.now(timezone.utc).isoformat()

    # Copy existing vector directly — avoids re-embedding and rate limits
    vector = raw.get("content_vector") or [0.0] * 1536

    return {
        "id": raw.get("id", ""),
        "file_name": raw.get("title") or raw.get("id", ""),
        "document_type": normalise_doc_type(raw.get("document_type", "")),
        "content": content,
        "content_vector": vector,
        "extracted_data": json.dumps(extracted, ensure_ascii=False) if extracted else None,
        "image_urls": [],
        "processed_at": processed_at,
        "odoo_record_id": None,
        "odoo_sync_status": None,
        "source_url": None,
        "whatsapp_number": None,
    }


def upsert_batch(docs: list[dict], client: httpx.Client) -> int:
    url = f"{DST_ENDPOINT}/indexes/{DST_INDEX}/docs/index?api-version=2024-07-01"
    headers = {"Content-Type": "application/json", "api-key": DST_KEY}
    body = {"value": [{"@search.action": "mergeOrUpload", **d} for d in docs]}
    resp = client.post(url, headers=headers, json=body, timeout=60)
    resp.raise_for_status()
    results = resp.json().get("value", [])
    succeeded = sum(1 for r in results if r.get("status"))
    return succeeded


def main():
    client = httpx.Client(timeout=60)

    print(f"Fetching all docs from {SRC_INDEX}...")
    raw_docs = fetch_all_docs(client)
    print(f"Found {len(raw_docs)} docs to migrate.\n")

    total_ok = 0
    total_err = 0
    batch = []

    for i, raw in enumerate(raw_docs, 1):
        try:
            doc = transform_doc(raw)
            batch.append(doc)
        except Exception as e:
            print(f"  [{i}] TRANSFORM ERROR {raw.get('id')}: {e}")
            total_err += 1
            continue

        if len(batch) >= BATCH_SIZE:
            ok = upsert_batch(batch, client)
            total_ok += ok
            print(f"  Upserted batch → {total_ok} succeeded so far")
            batch = []
            time.sleep(0.5)  # avoid throttling

    # Flush remaining
    if batch:
        ok = upsert_batch(batch, client)
        total_ok += ok

    print(f"\nDone. {total_ok} migrated, {total_err} errors.")
    client.close()


if __name__ == "__main__":
    main()
