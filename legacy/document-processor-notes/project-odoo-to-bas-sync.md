---
name: project-odoo-to-bas-sync
description: "PENDING: daily sync from Odoo → BAS properties-index (AI Search). Verified 2026-07-28 against live code — location, schema, sourceWebUrl, and 3-types-vs-1-index gap all resolved."
metadata: 
  node_type: memory
  type: project
  originSessionId: 891207d7-408b-4a10-81c0-dc230996dd60
  modified: 2026-07-28T03:43:29.362Z
---

## What needs to be built
A daily sync job that reads confirmed Odoo listings (`x_c21_listing`) and writes
them into the BAS project's `properties-index` on Azure AI Search. This feeds the
BAS Teams chatbot's `search_properties` tool (via [[project-odoo-to-bas-sync]] plan below).
Relates to [[project-odoo-source-of-truth]] — Odoo is the review gate before anything
becomes searchable.

## Repo layout correction (2026-07-28)
`etl-pipeline` is a **top-level sibling** of `business-automation-system` inside
`bas-stacks/`, NOT nested inside it as previously recorded:
```
bas-stacks/
├── etl-pipeline/          # owns properties-index + agents-index, has loader.py, Function App
├── business-automation-system/
│   ├── ai-agent/          # search_properties tool, reads properties-index
│   ├── agent-runtime/     # orchestrator — decides what's shown to the user
│   └── teams-agent/       # Teams channel adapter
├── onedrive-sync/         # captures OneDrive webUrl into blob metadata at upload time
```

## Confirmed properties-index schema (`etl-pipeline/scripts/create_search_indexes.py`)
| Field | Type | Notes |
|---|---|---|
| id | String (key) | |
| sourceBlob | String, filterable | **internal only — never shown to the user** |
| sourceWebUrl | String | the link actually surfaced to users |
| docType | String, filterable/facetable | |
| district | String, filterable/facetable | free-text, LLM-extracted, no fixed vocabulary |
| propertyType | String, filterable/facetable | lowercase convention ("office", "retail", ...) |
| transactionType | String, filterable/facetable | "rent"/"sale"; `search_properties.py` maps "lease"→"rent" as a synonym |
| listingDate | DateTimeOffset, filterable/sortable | |
| price | Double, filterable/sortable | |
| area_sqft | Double, filterable/sortable | |
| bedrooms | Int32, filterable/facetable | |
| bathrooms | Int32, filterable | |
| agentName | String, filterable | |
| content | Searchable (en.microsoft analyzer) | |
| address | Searchable | title field for semantic config |
| imageCaption | Searchable | |
| imageTags | Collection(String), filterable/facetable | |
| contentVector | Collection(Single), 3072 dims | `text-embedding-3-large`, HNSW profile "vector-profile" |

Semantic config name is **`"default"`** (not `"default-semantic-config"` as previously recorded).

## Finding: does BAS point users to a blob, or something else?
**Not a blob.** Confirmed in `agent-runtime/src/orchestrator.py:317-336`
(`_collect_related_media`): only items with a resolvable `sourceWebUrl` are ever
passed to the channel adapter — the comment literally says "a channel adapter
can't do anything useful with a bare internal blob path." `sourceBlob` is used
internally in `search_properties.py` (`map_search_hit`, `build_related_media`,
`_media_kind`) for dedup and media-kind classification, but is stripped before
the tool response reaches the LLM/user (`strip_internal_fields`).

For BAS's own ETL-sourced documents, `sourceWebUrl` is populated from the
**original OneDrive `webUrl`**, captured as blob metadata at ingest time:
`onedrive-sync/src/blob_uploader.py:69` sets `metadata["source_web_url"] = web_url`
→ carried through `etl-pipeline/src/doc_extractor.py:46` and `image_extractor.py:41`
→ written to the index as `sourceWebUrl` in `loader.py:132,307`.

**So the real gap for Odoo-sourced records isn't "not stored in blob" — Odoo
listings were never blob-stored and don't need to be.** The gap is that
`odoo_sync.py` (document-processor repo) already generates a working, clickable
document link (`doc_url`, an Odoo Documents share link) at write time, but only
ever embeds it as HTML inside `x_c21_notes` (`odoo_sync.py:454-457, 589-591`) —
never as a clean, queryable field. The sync job needs a real field to read from.

**Fix:** add a plain char field `x_c21_doc_url` to `x_c21_listing`, write the
existing `doc_url` value there alongside (or instead of) the notes HTML, and map
it straight to `sourceWebUrl` in the sync job. `sourceBlob` can stay empty for
Odoo-sourced rows — it's never rendered to a user on this index either way.

## Odoo → BAS field mapping
| Odoo field (`x_c21_listing`) | BAS field | Notes |
|---|---|---|
| x_name / x_c21_address | address | prefer x_c21_address if populated |
| x_c21_district | district | Odoo stores snake_case keys (`sheung_wan`) — map to English label via a lookup built from the reverse of `DISTRICT_MAP` in `odoo_sync.py` |
| x_c21_property_type | propertyType | already English keys via `PROPERTY_TYPE_MAP`, confirm lowercase |
| x_c21_rent_net | price | monthly rent |
| x_c21_size_sqft | area_sqft | direct |
| x_c21_contact_name | agentName | direct |
| x_c21_date_received | listingDate | date string → DateTimeOffset |
| x_c21_floor_unit | part of `content` | append, not a dedicated field on BAS side |
| (new) x_c21_doc_url | sourceWebUrl | see finding above |
| (missing today) | transactionType | no Odoo field yet — default `"rent"` until one exists |

## Remaining real gaps (in dependency order)
1. **No review gate.** Every Odoo listing gets `x_c21_status="active"` at
   creation (`odoo_sync.py:418,507`) — there's no field marking a record
   human-reviewed/ready to publish. Per [[project-odoo-source-of-truth]] the
   daily-sync delay is supposed to exist *because* of human review; without a
   gate field, syncing "active" records would just re-create direct
   pipeline→index publishing, which was deliberately removed. **Blocks
   everything else.** Needs a new boolean field, e.g. `x_c21_ready_to_publish`
   (default False), flipped by a human — likely as part of the still-pending
   Manual Data Editor work.
2. **x_c21_doc_url field** (see finding above) — small, unblocked, can do anytime.
3. **transactionType** — either accept the "always rent" default or add a real
   Odoo field once sale listings exist.
4. **Stable id** — BAS's own loader keys off `md5(blob_path)`; Odoo records have
   no blob path. Use `f"odoo-listing-{record_id}"` as the Search doc key, fed to
   `merge_or_upload_documents` for idempotent upsert.
5. **Incremental cursor** — filter Odoo by `write_date` against a stored
   high-water mark so the daily job only re-embeds changed records.
6. imageCaption/imageTags — leave null, lower priority, no image pipeline on the Odoo side.

## Finding: document processor has 3 destinations, BAS vector search effectively has 1
Confirmed (2026-07-28) by grepping every `get_search_client(...)` call site and every
tool file under `ai-agent/src/tools/`:

**Document processor's classifier produces 5 document types that route to 3 different
Odoo destinations:** `listing`/`listing_list`/`pitching_deck` → `x_c21_listing`
(property), `news` → Odoo Knowledge article (`knowledge_sync.py`), `contact` →
Odoo `res.partner` (`contact_sync.py`).

**BAS's search side has exactly 2 indexes defined** (`etl-pipeline/scripts/create_search_indexes.py`):
`properties-index` (docTypes `property_listing`/`property_detail`/`fa_report`/`property_photo`)
and `agents-index` (docType `name_card`). But **only `properties-index` is actually
queryable today** — `search_properties.py` is the only tool anywhere in
`business-automation-system` that calls `get_search_client(...)`, and it hardcodes
`"properties-index"`. `agents-index` is populated by `loader.py` on `name_card` docs
but no tool reads it — it exists in schema and gets written to, but nothing in the
agent's tool surface queries it. There's a separate, real path for agent/contact data
that IS live: `get_property_context.py` reads agent info out of **Cosmos DB**
(`entities` container, `partition_key="Agent"`), linked via `agentId` on the property
entity — not via `agents-index` search at all.

**There is no BAS index for `news`/knowledge-article content at all.** Nothing in
`etl-pipeline` or `ai-agent` references a third index; `_INDEX_MAP` in `loader.py`
only ever resolves to `properties-index` or `agents-index`.

### What this means for the Odoo→BAS sync
1. **`property` records** (the sync job planned above) → `properties-index`. This is
   the only one with a live read path in the BAS agent today — build this first.
2. **`contact` records** (Odoo `res.partner`, synced by `contact_sync.py`) → BAS
   doesn't search these via `agents-index` at all; it reads agent data from **Cosmos
   `entities`** instead. So syncing contacts into `agents-index` would populate a
   dead-end nobody queries. If contacts need to reach the BAS agent, the target
   should be **Cosmos `entities` (partition `Agent`)**, matching `agentId` linkage
   convention on property entities — not `agents-index`.
3. **`news`/knowledge-article records** → no destination exists on BAS's side at all.
   Either out of scope for this sync (news stays Odoo-only, doesn't need to reach the
   BAS property/leasing agent), or a new index + tool needs to be designed and built —
   that's new scope, not a mapping gap.

**Suggestion:** scope the daily sync to `property` only for v1, matching the one
destination that's actually live end-to-end (index populated *and* queried). Treat
contact→Cosmos and news→(new index, if ever needed) as separate, explicitly-scoped
follow-ups rather than silently dropping them into indexes nothing reads.

## Where the job should live
**Recommend building it inside `bas-stacks/etl-pipeline`** (new timer trigger,
e.g. `src/odoo_sync_job.py`), not in the document-processor's Function App —
`etl-pipeline` already has managed-identity auth to the correct Azure OpenAI
`text-embedding-3-large` deployment and the correct Search service for
`properties-index`; building it on the document-processor side would require
provisioning cross-tenant credentials for a service it doesn't otherwise touch.
The job talks to Odoo via XML-RPC, same pattern as `odoo_sync.py` in the
document-processor repo (`ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME`, `ODOO_API_KEY`).

## How to apply
When resuming this work: gap #1 (review gate field) is the actual prerequisite —
build that first, or explicitly decide to sync on `x_c21_status='active'` alone
as a temporary/manual filter while the review UI doesn't exist yet. Everything
else (#2–6) is mechanical once the gate exists.
