"""Migrate property-intel-index from text-embedding-3-small (1536d) to text-embedding-3-large (3072d).

Steps:
  1. Read all docs from the current index
  2. Delete the index
  3. Recreate it with 3072-dim schema
  4. Re-embed each doc's content with text-embedding-3-large
  5. Upload all docs back

Run from the langgraph/ directory:
    source .venv/bin/activate
    python scripts/migrate_embeddings_to_large.py

Prerequisites:
  - AZURE_OPENAI_EMBEDDING_DEPLOYMENT must be set to "text-embedding-3-large" in .env
    (or pass --deployment text-embedding-3-large on the command line)
  - text-embedding-3-large must be deployed in your Azure OpenAI resource
"""

import argparse
import json
import os
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SEARCH_ENDPOINT = os.environ["AZURE_SEARCH_ENDPOINT"]
SEARCH_API_KEY = os.environ["AZURE_SEARCH_API_KEY"]
INDEX_NAME = os.environ.get("AZURE_SEARCH_INDEX", "property-intel-index")

OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
OPENAI_KEY = os.environ["AZURE_OPENAI_KEY"]

NEW_DIMENSIONS = 3072

SEARCH_HEADERS = {
    "Content-Type": "application/json",
    "api-key": SEARCH_API_KEY,
}
OPENAI_HEADERS = {
    "Content-Type": "application/json",
    "api-key": OPENAI_KEY,
}

# ---------------------------------------------------------------------------
# New index schema (3072 dims — everything else identical to indexer.py)
# ---------------------------------------------------------------------------

NEW_INDEX_SCHEMA = {
    "name": INDEX_NAME,
    "fields": [
        {"name": "id", "type": "Edm.String", "key": True, "searchable": False},
        {"name": "file_name", "type": "Edm.String", "searchable": True, "filterable": True},
        {"name": "document_type", "type": "Edm.String", "searchable": False, "filterable": True, "facetable": True},
        {"name": "content", "type": "Edm.String", "searchable": True},
        {
            "name": "content_vector",
            "type": "Collection(Edm.Single)",
            "searchable": True,
            "dimensions": NEW_DIMENSIONS,
            "vectorSearchProfile": "default-profile",
        },
        {"name": "extracted_data", "type": "Edm.String", "searchable": True},
        {"name": "building_name", "type": "Edm.String", "searchable": True, "filterable": True},
        {"name": "image_urls", "type": "Collection(Edm.String)", "searchable": False, "filterable": False},
        {"name": "processed_at", "type": "Edm.DateTimeOffset", "searchable": False, "filterable": True, "sortable": True},
        {"name": "sell_price", "type": "Edm.Int64", "searchable": False, "filterable": True, "sortable": True},
        {"name": "return_rate", "type": "Edm.Double", "searchable": False, "filterable": True, "sortable": True},
        {"name": "transaction_type", "type": "Edm.String", "searchable": False, "filterable": True, "facetable": True},
        {"name": "extraction_path", "type": "Edm.String", "searchable": False, "filterable": True, "facetable": True},
        {"name": "needs_review", "type": "Edm.Boolean", "searchable": False, "filterable": True},
        {"name": "odoo_record_id", "type": "Edm.String", "searchable": False, "filterable": True},
        {"name": "odoo_sync_status", "type": "Edm.String", "searchable": False, "filterable": True},
        {"name": "source_url", "type": "Edm.String", "searchable": False, "filterable": False},
        {"name": "whatsapp_number", "type": "Edm.String", "searchable": False, "filterable": True, "facetable": True},
    ],
    "vectorSearch": {
        "profiles": [{"name": "default-profile", "algorithm": "default-algorithm"}],
        "algorithms": [
            {
                "name": "default-algorithm",
                "kind": "hnsw",
                "hnswParameters": {"m": 4, "efConstruction": 400, "efSearch": 500, "metric": "cosine"},
            }
        ],
    },
    "semantic": {
        "configurations": [
            {
                "name": "default-semantic-config",
                "prioritizedFields": {
                    "titleField": {"fieldName": "file_name"},
                    "prioritizedContentFields": [{"fieldName": "content"}],
                    "prioritizedKeywordsFields": [{"fieldName": "extracted_data"}],
                },
            }
        ]
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _search_url(path: str) -> str:
    return f"{SEARCH_ENDPOINT}{path}"


def fetch_all_docs(client: httpx.Client) -> list[dict]:
    """Page through the index and return every document (excluding content_vector)."""
    docs = []
    url = _search_url(f"/indexes/{INDEX_NAME}/docs/search?api-version=2024-07-01")
    # Fetch all fields except the old vector (we'll regenerate it)
    body = {
        "search": "*",
        "select": "id,file_name,document_type,content,extracted_data,building_name,"
                  "image_urls,processed_at,sell_price,return_rate,transaction_type,"
                  "extraction_path,needs_review,odoo_record_id,odoo_sync_status,"
                  "source_url,whatsapp_number",
        "top": 1000,
    }

    while url:
        resp = client.post(url, headers=SEARCH_HEADERS, json=body)
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("value", [])
        docs.extend(batch)
        print(f"  fetched {len(docs)} docs so far...")

        # Follow @odata.nextLink for pagination
        next_link = data.get("@odata.nextLink")
        if next_link:
            url = next_link
            body = None  # nextLink already encodes all params
        else:
            url = None

    return docs


def delete_index(client: httpx.Client) -> None:
    url = _search_url(f"/indexes/{INDEX_NAME}?api-version=2024-07-01")
    resp = client.delete(url, headers=SEARCH_HEADERS)
    if resp.status_code == 404:
        print("  index not found, nothing to delete")
        return
    resp.raise_for_status()
    print(f"  deleted index '{INDEX_NAME}'")


def create_index(client: httpx.Client) -> None:
    url = _search_url("/indexes?api-version=2024-07-01")
    resp = client.post(url, headers=SEARCH_HEADERS, json=NEW_INDEX_SCHEMA)
    resp.raise_for_status()
    print(f"  created index '{INDEX_NAME}' with {NEW_DIMENSIONS} dims")


def get_embedding(client: httpx.Client, text: str, deployment: str) -> list[float]:
    url = f"{OPENAI_ENDPOINT}/openai/deployments/{deployment}/embeddings?api-version=2024-02-01"
    resp = client.post(url, headers=OPENAI_HEADERS, json={"input": text[:8000]}, timeout=30)
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]


def upload_batch(client: httpx.Client, docs: list[dict]) -> None:
    url = _search_url(f"/indexes/{INDEX_NAME}/docs/index?api-version=2024-07-01")
    body = {"value": [{"@search.action": "upload", **doc} for doc in docs]}
    resp = client.post(url, headers=SEARCH_HEADERS, json=body, timeout=60)
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate embeddings to text-embedding-3-large")
    parser.add_argument(
        "--deployment",
        default=os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large"),
        help="Azure OpenAI embedding deployment name (default: text-embedding-3-large)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch docs and show count, but do NOT delete/recreate the index",
    )
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  Migration: {INDEX_NAME}")
    print(f"  Embedding: {args.deployment} ({NEW_DIMENSIONS} dims)")
    print(f"  Endpoint:  {SEARCH_ENDPOINT}")
    print(f"{'='*60}\n")

    client = httpx.Client(timeout=60)

    # ── Step 1: fetch all docs ──────────────────────────────────────────────
    print("Step 1/5: Fetching all documents...")
    docs = fetch_all_docs(client)
    print(f"  Total docs: {len(docs)}\n")

    if not docs:
        print("No documents found. Exiting.")
        sys.exit(0)

    if args.dry_run:
        print("DRY RUN — stopping here. No changes made.")
        for d in docs[:5]:
            print(f"  • {d.get('file_name')} ({d.get('document_type')})")
        if len(docs) > 5:
            print(f"  ... and {len(docs) - 5} more")
        sys.exit(0)

    # ── Confirm before destructive steps ───────────────────────────────────
    confirm = input(f"About to DELETE and RECREATE '{INDEX_NAME}'. Continue? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        sys.exit(0)

    # ── Step 2: delete index ────────────────────────────────────────────────
    print("\nStep 2/5: Deleting index...")
    delete_index(client)
    time.sleep(2)  # brief pause for Azure propagation

    # ── Step 3: recreate with 3072 dims ────────────────────────────────────
    print("\nStep 3/5: Recreating index (3072 dims)...")
    create_index(client)
    time.sleep(2)

    # ── Step 4: re-embed and upload ─────────────────────────────────────────
    print(f"\nStep 4/5: Re-embedding {len(docs)} documents with {args.deployment}...")
    batch: list[dict] = []
    errors: list[str] = []

    for i, doc in enumerate(docs, 1):
        file_name = doc.get("file_name", doc.get("id", "?"))
        content = doc.get("content") or ""

        try:
            vector = get_embedding(client, content, args.deployment)
        except Exception as e:
            print(f"  [{i}/{len(docs)}] ERROR embedding '{file_name}': {e}")
            errors.append(file_name)
            continue

        # Remove @search.score and other read-only fields Azure adds
        clean_doc = {k: v for k, v in doc.items() if not k.startswith("@")}
        clean_doc["content_vector"] = vector

        batch.append(clean_doc)

        # Upload in batches of 50
        if len(batch) >= 50:
            upload_batch(client, batch)
            print(f"  [{i}/{len(docs)}] uploaded batch of {len(batch)}")
            batch = []
        else:
            print(f"  [{i}/{len(docs)}] embedded '{file_name}'")

    # Upload remaining docs
    if batch:
        upload_batch(client, batch)
        print(f"  uploaded final batch of {len(batch)}")

    # ── Step 5: summary ─────────────────────────────────────────────────────
    print(f"\nStep 5/5: Done.")
    print(f"  Migrated: {len(docs) - len(errors)}/{len(docs)} documents")
    if errors:
        print(f"  Failed ({len(errors)}):")
        for name in errors:
            print(f"    • {name}")

    print(f"\nNext steps:")
    print(f"  1. Update AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large in App Service env vars")
    print(f"  2. Update indexer.py INDEX_SCHEMA dimensions from 1536 → 3072")
    print(f"  3. Deploy both App Services so new documents use 3072-dim embeddings")
    print(f"  4. Redeploy Azure Function with updated env var\n")


if __name__ == "__main__":
    main()
