# Document Processor - Development Rules

## Project Overview
LangGraph + LangSmith document processor.

> **ARCHITECTURE NOTE (2026-07-28, verified against live code):** The pipeline is now a
> **v2 Odoo-ingest service** — see `src/graph.py` docstring, the source of truth. Single
> entry point `process_file_from_bytes()`. Documents arrive from WhatsApp/Slack (via n8n)
> only [**UPDATE 2026-09-15: OneDrive is now a fourth channel, see below — this
> "no OneDrive timer" line is stale, kept for context on why the OLD v1 timer/full-listing
> approach was removed**]. **No Azure AI Search writes from this repo.** The RAG chatbot
> (`src/nodes/chatbot.py`), `/api/chat`, `/api/search`, and the `prop-chat` App Service
> are **removed/stopped** — sections below describing them (Graph 2, chat routes, Next.js
> Chat/Search pages) are historical and do not reflect what's deployed. Only two routers
> are live: `api/routes/admin.py` and `api/routes/assistant.py`
> (`api/doc_pipeline_main.py`). The document-processor's own Azure AI Search index
> (`property-intel-index`, confirmed live on `c21net-bas-srch-ea-prod`,
> `text-embedding-3-large`, 3072 dims) is being deprecated in favor of the separate BAS
> project's `properties-index` on the same search service — see memory
> `project-odoo-to-bas-sync.md` for the migration plan.

> **UPDATE (2026-09-13): Microsoft Teams is now a third live channel**, verified
> end-to-end (see Session Summary below) — `api/routes/teams.py` (inbound Bot
> Framework `/api/messages`), `src/utils/teams_notify.py` (async completion via Bot
> Connector REST), `src/utils/teams_conversations.py` (ConversationReference
> persistence), `teams-app-package/` (Teams app manifest). **Not** the same thing as
> `bas-stacks`' separate "C21net Property AI Agent (ALT)" Teams bot (property search,
> unrelated codebase/app registration, `supportsFiles: false`) — see memory
> `reference-org-chatbot-map.md`.
>
> This had actually been deployed out-of-band (manually copied to both services'
> wwwroot/package, no git commit) since at least 2026-09-12, but was undocumented
> and untested end-to-end until this session. Now committed (`498a17d`, `fe29121`)
> and confirmed working: a real SharePoint file-share attachment resolves correctly
> via `_download_attachment()`'s `application/vnd.microsoft.teams.file.download.info`
> path (the "attachments empty" case from the original 2026-09-12 diagnostic did not
> reproduce for this sharing method — may still exist for other Teams attachment
> shapes, not fully ruled out), the pipeline completes, Odoo gets accurate data, and
> — after this session added the previously-missing `MICROSOFT_APP_ID`/
> `MICROSOFT_APP_PASSWORD`/`MICROSOFT_APP_TENANT_ID` app settings on the **Function
> App** (`c21net-bas-func-doc-pipeline-ea-prod` — they already existed on the App
> Service, which is why the bug was easy to miss) — the completion message now
> actually reaches the user back in Teams.

> **UPDATE (2026-09-15): OneDrive is now a fourth live ingest channel**, added as a
> Function App timer trigger — `onedrive_sync` (`function_app.py`, once daily 23:00 UTC / 07:00 HKT — was every 10 min during initial testing, see 2026-09-16 addendum below) —
> feeding into the **same** `enqueue_pipeline_job()` → `pipeline_job_worker` → LangGraph
> → Odoo path every other channel uses (`source="onedrive"` in `DocumentState`, no new
> pipeline logic). New files dropped in `MS_GRAPH_INBOX_FOLDER` (`/Document Processor/In`)
> get picked up automatically; **no notification is sent back per-file** (there's no
> WhatsApp/Slack sender to reply to) — see the daily digest below instead.
>
> **Delta-based, not the old v1 full-folder-listing approach** — `src/utils/graph_client.py`
> (Microsoft Graph `/delta` API) + `src/utils/onedrive_delta_store.py` (persisted delta
> link in Table Storage, table `OneDriveSyncState`). This is the key safety property: the
> timer only ever asks Graph "what changed since this token", so the **existing backlog is
> never reprocessed** — verified live, the one-time baseline (`scripts/onedrive_baseline_delta.py`,
> run 2026-09-15) found and discarded **29 existing files** in `/In` before saving the
> baseline token; only files added after that point will ever be picked up. The old,
> since-deleted `src/nodes/onedrive.py` (full listing + move-to-`/Processed`) is NOT what
> this reuses — recoverable via `git show a16b49a:src/nodes/onedrive.py` for reference only,
> do not resurrect that pattern.
>
> **Guards, all live:** hard-stops (raises, alerts, no silent full resync) if the delta link
> is ever missing or Graph returns 410 expired — mirrors the same incident-driven guard in
> the sibling `bas-stacks` project's `onedrive-sync` Function App (see that repo's
> `RUNBOOK-backfill.md` for the "re-OCR the whole drive" incident this pattern avoids).
> `ONEDRIVE_SYNC_MAX_AGE_DAYS` (90) bounds a legitimate delta response; `SUPPORTED_FORMATS`
> + `ONEDRIVE_MAX_FILE_MB` (25) filter before enqueueing; the existing DI daily-page guard
> (`di_guard.py`, unchanged) still applies automatically since this is the same
> `process_file_from_bytes()` call — **the DI cap is shared across all four channels, not
> per-channel**, worth watching if OneDrive volume turns out to be high. Master off-switch
> `ONEDRIVE_SYNC_ENABLED` — **currently `true`** (flipped on 2026-09-15 after baseline).
>
> **New daily digest** — `daily_processing_summary` (`function_app.py`, cron
> `0 55 15 * * *` = 15:55 UTC = 23:55 HKT; Linux Function Apps run cron in UTC regardless
> of `WEBSITE_TIME_ZONE`, so the HKT offset is baked into the cron expression itself, not
> left to app settings — got this wrong once already this session, fixed same day) posts a
> daily rollup (`count_runs_today()` in `table_storage.py` + `di_guard.get_usage_today()`)
> to Slack channel `#doc-processor-alerts` (`ADMIN_SLACK_CHANNEL=C0C1HJDUJR5`, C21net
> workspace — **not** `#all-c21net`, and not the same as any per-document completion
> reply). **Always sends, even with zero activity** — deliberate, a missing message is
> itself the signal the schedule/app has stopped, not just "quiet day."
>
> Commits: `f0daad0` (feature), `8ec3c5b` (timezone fix). Both deployed via
> `./deploy.sh --func-only` — no App Service changes were needed for either.
>
> **Addendum (2026-09-16):** two more real issues found and fixed same day, both via direct
> Application Insights queries against `c21net-bas-func-doc-pipeline-ea-prod`, not
> assumption:
> 1. **`onedrive_sync` crashed on every single run** (`ModuleNotFoundError: No module named
>    'api'`) — it imported `SUPPORTED_FORMATS` from `api.common`, but `.funcignore`
>    deliberately excludes the entire `api/` package from the Function App deployment
>    (keeps FastAPI/heavy deps out of it, pre-existing rule, not new this session). Moved
>    the constant to `src/utils/supported_formats.py` (not excluded, used by both services);
>    `api/common.py` now just re-exports it. Fixed in `61bd485`, verified live: the first
>    execution on the corrected package (`2026-09-16T02:00:14Z`) shows `Succeeded` in App
>    Insights, vs. `Failed` on every prior run.
> 2. **Cadence changed from every 10 min to once daily** (`0 0 23 * * *` = 23:00 UTC =
>    07:00 HKT) at the user's request — OneDrive doesn't need WhatsApp/Slack/Teams-level
>    responsiveness. Matches the sibling `bas-stacks` project's own `onedrive-sync`
>    schedule (`0 0 7 * * *` there) in intent, but **not** in mechanism: bas-stacks relies
>    on `WEBSITE_TIME_ZONE=Asia/Singapore` to make `7` mean 7am local, which this session
>    could not empirically confirm actually works (couldn't locate that Function App's
>    execution logs in the time spent); this repo's own Function App has no
>    `WEBSITE_TIME_ZONE` set and was directly proven to run cron in raw UTC (see the
>    timezone-fix note above) — so the HKT offset is baked into the cron expression itself
>    here, not left to an app setting that may or may not be honored.
>
> Both lessons generalize: **query Application Insights to verify a Function App change
> actually took effect and actually works — a successful `./deploy.sh` / "Remote build
> succeeded!" message proves the code shipped, not that it runs correctly.** This session
> caught both issues that way, not by inspection alone.

> **Addendum 2 (2026-09-16, same day): watched folder was wrong; source-tracking added;
> a real n8n bug found; one more deploy gotcha.**
>
> **Folder repointed — `Document Processor/In` was the wrong target.** That folder
> (`admin@c21net.com`'s own OneDrive) turned out to be a dormant leftover from the v1
> pipeline — only 29 stale files, no real activity. The sibling `bas-stacks` project
> already proved the *actual* live folder: Stephen Wong's OneDrive,
> `Building_Folder/BD_Commercial` (confirmed by resolving both Graph item IDs directly —
> they're the same folder `bas-stacks`' ETL watches). Repointed there via two new
> dedicated env vars, `ONEDRIVE_SYNC_DRIVE_ID` / `ONEDRIVE_SYNC_FOLDER_PATH` — **not**
> reusing `MS_GRAPH_DRIVE_ID`/`MS_GRAPH_INBOX_FOLDER`, which `scripts/process_inbox.py`,
> `scripts/check_onedrive.py`, and the admin config route also read; repointing those
> globally would have silently affected unrelated legacy code paths. Re-baselined against
> the new folder: **7,099 existing files found and confirmed discarded** (not the ~29 from
> before) — a manual `onedrive_sync` invocation immediately after found exactly 0 changed
> files against that real backlog, and `DI_pages_used_today` stayed at 0 throughout, so no
> AI cost was incurred re-scanning it. This session's own app registration (same
> `MS_GRAPH_CLIENT_ID`) already had read access to Stephen Wong's drive with zero new
> consent/permission changes — Graph application permissions are tenant-wide by design.
>
> **n8n "Slack Integration" workflow (`DJkAX2NYNHcncFis`) had a real bug**, found when
> inviting the bot to the new `#doc-processor-alerts` channel triggered a false "⏳ 正在處理"
> + greeting-menu response with no actual message sent. Root cause: the `Is Human Message?`
> filter node only excluded `bot_message`/`message_changed` subtypes — a `channel_join`
> system event (bot_id empty, subtype neither excluded value) passed straight through as if
> it were real content. Fixed by adding `channel_join`/`channel_leave`/`channel_topic`/
> `channel_purpose`/`channel_name` to the exclusion list and publishing the new version —
> matters because this bot watches the whole workspace (`watchWorkspace: true`), so it will
> get invited to channels again in the future.
>
> **`ProcessingHistory` never recorded which channel processed a document, for any channel,
> since the table was first built (2026-07-17)** — not a regression, a field that simply
> never existed until now. Added `source` to `log_run()` (`table_storage.py`) and threaded
> `DocumentState.source` through in `graph.py` (the one call site missing it);
> `count_runs_today()` now also returns `manual_success`/`manual_error` (WhatsApp/Slack/
> Teams) and `onedrive_success`/`onedrive_error`, bucketing pre-existing rows with no stored
> source as "manual" (accurate — OneDrive is the only channel that didn't already exist).
> The daily digest now shows this split as two extra lines.
>
> **Deploy gotcha, new this session:** a package swap completing (confirmed via
> `packagename.txt` updating) is **not sufficient on its own** — a live test right after a
> `--all` deploy still returned the *old* digest format (no breakdown lines) even though the
> new package had already swapped in seconds earlier. The Python worker process needed an
> explicit `az functionapp restart` before it actually picked up the new code. Add this to
> the existing "don't trust deploy success at face value" lesson above: **verify behavior
> with a real invocation after a deploy, and if it doesn't match, try a restart before
> assuming the deploy itself failed.**
>
> Commits: `77b15bb` (folder repoint), `a647306` (source-tracking + digest breakdown).

- **Document pipeline:** WhatsApp/Slack/Teams/OneDrive → n8n (WhatsApp/Slack), Bot Framework (Teams), or the `onedrive_sync` timer → `handle_message()`/`enqueue_pipeline_job()` → LangGraph → Odoo
- **Teams:** Teams user → Bot Framework → `POST /api/messages` (`api/routes/teams.py`) → same channel-agnostic `handle_message()` core → async completion via `teams_notify.py`, requires `MICROSOFT_APP_ID`/`PASSWORD`/`TENANT_ID` on **both** the App Service and the Function App (job_queue.py's async notify runs in the Function App)
- **OneDrive:** `onedrive_sync` timer (Function App, once daily 07:00 HKT) → Graph delta → `enqueue_pipeline_job(source="onedrive")` → same queue as every other channel; no per-file notify, see daily Slack digest instead
- **Backend API:** FastAPI on Azure App Service (see FastAPI Backend section)

## Product Design Philosophy

- **Users never see a terminal** — background service
- **Users interact with OneDrive** — drop files in `/In`, find results in `/Processed`
- **LangSmith is the monitoring UI** — traces, errors, debugging
- **Dashboard Ingest** — users can drop PDF, Word, PowerPoint, JPG, PNG in Admin → Ingest tab; AI triages each file before processing

## Development Rules

### 1. Testing
- Test command: `cd langgraph && source .venv/bin/activate && pytest -v`
- All new nodes must have corresponding tests
- Use mocks for external Azure services in unit tests

### 2. Code Standards
- Python 3.11+, type hints throughout
- Dataclasses for state objects
- `@traceable` decorator on all nodes for LangSmith observability

### 3. Project Structure
```
langgraph/
├── src/
│   ├── nodes/          # Processing nodes
│   │   ├── chatbot.py  # RAG chatbot (production)
│   │   └── report_generator/  # PDF report generation
│   ├── state.py        # DocumentState schema
│   ├── graph.py        # Workflow graph
│   ├── config.py       # Configuration
│   └── utils/
│       ├── json_parser.py     # Shared JSON parsing
│       ├── blob_storage.py    # Azure Blob upload
│       ├── table_storage.py   # Azure Table Storage — permanent history log
│       ├── job_queue.py       # Durable pipeline job queue (enqueue + worker + notify)
│       ├── file_cache.py      # Blob-backed pending-file cache (WhatsApp confirmations)
│       ├── di_guard.py        # Document Intelligence daily cost guard
│       ├── whatsapp_notify.py # WhatsApp send via n8n notify webhook
│       ├── slack_notify.py    # Slack send via Bot token
│       ├── channel_notify.py  # Single dispatch point: channel name -> notify fn (whatsapp/slack/teams)
│       ├── teams_notify.py    # Teams proactive-message send via Bot Framework REST (needs MICROSOFT_APP_ID/PASSWORD/TENANT_ID on the Function App)
│       ├── teams_conversations.py # Persists Teams ConversationReference for async notify
│       ├── bas_index_sync.py  # Immediate Odoo->BAS properties-index sync on every ingest (daily odoo-bas-sync job still runs as reconciliation)
│       └── session_storage.py # Assistant session persistence (Table Storage)
├── api/
│   ├── main.py         # FastAPI app entry point
│   ├── auth.py         # JWT auth + bcrypt + rate limiting
│   └── routes/
│       ├── chat.py     # /api/chat (stream, report)
│       ├── search.py   # /api/search
│       ├── admin.py    # /api/admin (triage, upload, process, vector, history)
│       └── teams.py    # Bot Framework /api/messages endpoint for Teams ingest — verified end-to-end 2026-09-13
├── tests/              # Mirror src structure
├── function_app.py     # Azure Functions (timer + HTTP)
└── .env                # Local secrets (never commit)

nextjs-dashboard/       # Next.js frontend (primary UI)
├── app/
│   ├── (app)/
│   │   ├── chat/       # Chat UI
│   │   ├── search/     # Keyword Search UI
│   │   └── admin/      # Upload / Processing / Vector DB / Settings
│   └── login/
├── components/
│   └── Sidebar.tsx
└── lib/
    └── api.ts          # All API calls (fetch wrapper with JWT)
```

### 4. Sprint Workflow
1. Implement feature
2. Write/update tests
3. Run `pytest -v` to verify
4. Check LangSmith traces for observability
5. Update README progress checklist

### 5. Environment
- Virtual env: `langgraph/.venv`
- Activate: `source .venv/bin/activate`
- Install: `pip install -e ".[dev]"`

### 6. Key Configurations
- LangSmith projects: `document-processor`, `property-chatbot`
- Azure region: Hong Kong / Sweden Central (OpenAI)
- Blob container: `property-pdf`

---

## Current Status
- [x] Project setup & LangSmith tracing
- [x] OneDrive integration (list files, get download URL, move files)
- [x] Azure Document Intelligence OCR
- [x] Folder watcher script (process_inbox.py)
- [x] AI Classification (listing/listing_list/pitching_deck/news/contact) via OpenRouter Qwen
- [x] Streamlit Dashboard (pulls data from LangSmith + Process Now button)
- [x] Data Extraction (structured fields via Qwen 2.5 72B)
- [x] Azure AI Search indexing (vector search with embeddings)
- [x] Azure Functions deployed (timer + HTTP triggers)
- [x] COMPLETE - Full pipeline running in Azure
- [x] RAG Chatbot (Property Intelligence Assistant)
- [x] Streaming responses (real-time answer display)
- [x] Hybrid Search (Vector + Web via Tavily)
- [x] Smart Query Router (vector/web/hybrid based on query type)
- [x] Semantic Ranking (Azure AI Search semantic configuration)
- [x] Pitching Deck support (comprehensive property marketing extraction)
- [x] Document Analysis (pre-extraction structure analysis)
- [x] Smart Index Merge (preserve existing data, don't overwrite with nulls)
- [x] Image Display (extract PDF images, store in blob, display in dashboard)
- [x] Report from Chat Results (generate PDF reports using chatbot search results)
- [x] Multi-Index Search (chatbot searches multiple Azure AI Search indexes)
- [x] Dashboard Upload (upload PDFs directly to OneDrive /In via dashboard)
- [x] Search REST API (external chatbots can query our search via `/api/search`)
- [x] Next.js Dashboard (replaced Streamlit as primary UI; deployed on Azure Static Web Apps)
- [x] FastAPI Backend (Azure App Service; JWT auth + bcrypt + rate limiting)
- [x] Chat "Generate Report PDF" button (Next.js → FastAPI → fpdf2)
- [x] Permanent Processing History (Azure Table Storage — survives LangSmith 14-day expiry)
- [x] Ingest Page with AI Triage (multi-format upload; AI identifies doc type before processing; unsupported files logged)
- [x] JWT sessions extended to 30 days
- [x] **OneDrive delta-sync as a fourth ingest channel** (2026-09-15) — see UPDATE note
      above. Delta-based (Graph `/delta`), baseline established (29 existing files
      skipped), guards live (DI daily cap, age/size/format filters, hard-stop on
      missing/expired delta link), `ONEDRIVE_SYNC_ENABLED=true` deployed. Daily Slack
      digest (`#doc-processor-alerts`) added alongside it for visibility since there's
      no per-file WhatsApp/Slack reply target for this channel.
- [ ] Manual Data Editor (edit extracted_data via form UI in Admin tab)
- [ ] Pipeline support for non-PDF formats (DOCX, PPTX, JPG ingested but pipeline currently OCRs as-is)
- [x] **Move the web dashboard to `genie.infiniduo.com`** (decided and
      completed 2026-09-11). `www.c21net.com` (`c21-leasing`) was explicitly
      NOT part of this and did not move (a domain-move item was briefly,
      incorrectly listed under `c21-leasing`'s CLAUDE.md on 2026-09-10 —
      corrected 2026-09-11).
      **How it was done:** `infiniduo.com`'s nameservers are Vercel's own
      (`ns1/ns2.vercel-dns.com` — confirmed via `dig NS infiniduo.com`), and
      the domain is registered under the same Vercel account/team
      (`lojuls-projects`) this dashboard's project lives in — so the whole
      move was one command, no external registrar/DNS step needed: `cd
      nextjs-dashboard && vercel domains add genie.infiniduo.com` (run from
      inside the project dir so it infers the target project). Routing was
      live within seconds since Vercel manages both ends.
      **The one extra step that's easy to miss:** the backend's CORS
      allowlist only holds one hardcoded origin (`DOC_PIPELINE_CORS_ORIGIN`
      / `FRONTEND_URL` app settings on `c21net-bas-api-doc-pipeline-ea-prod`
      — see the 2026-09-10 CORS gotcha above) — updating it to
      `https://genie.infiniduo.com` triggers the same App Service restart +
      ~1-2 min propagation delay seen before. This also means the OLD
      `nextjs-dashboard-kappa-one-24.vercel.app` URL still loads (Vercel
      doesn't remove prior URLs) but its chat feature now fails CORS — that
      old URL is effectively retired, not actively maintained going forward.
      Verified end-to-end: logged in fresh at `genie.infiniduo.com/chat/`
      and got a real assistant reply.
- [x] **Marketing landing page at the root** (completed 2026-09-11, revised
      twice same day after user feedback — see corrections below). Root `/`
      previously hard-redirected straight to `/chat` (`app/page.tsx` was
      just `redirect("/chat")`) — the domain had no actual front page, only
      the login-gated app.
      **How it was built:** drafted first in Lovable (`create_project`,
      workspace `julianlau's Lovable`, project id
      `c415b9c8-3901-411b-97a6-dade75086674`, display name "Genie: Your
      Property AI" — name is now stale, see correction #2 below) using
      `https://postcraft.infiniduo.com` (`soshio-landing` repo) as the
      style/structure reference — warm cream background, bold headline with
      one italic accent word, pill nav CTA, mock chat-preview panel,
      numbered "How it works", feature grid, final CTA, minimal footer. The
      Lovable draft is left as-is (private, not published, and NOT updated
      with the corrections below) — it was a one-time design reference, not
      the deployed artifact; don't treat it as current.
      **Ported into this repo directly** (`app/page.tsx`, plus new fonts in
      `app/layout.tsx` — Instrument Serif italic for the accent word, Noto
      Sans TC for Chinese — and a `genie-*` color palette added to
      `app/globals.css`) rather than cross-hosting a second app under the
      same domain — kept everything on one deploy, no extra CORS/domain
      surface. Added `lucide-react` for icons (only page in this repo that
      uses it).
      **The app itself is untouched** — `/login`, `/chat`, `/admin/*` etc.
      all work exactly as before; they're just no longer what `/` shows
      automatically. "Sign in" buttons on the landing page link to `/login`.

      **Correction #1 (same day):** the final CTA section used a near-black
      background (`bg-genie-ink`) that clashed with the rest of the warm
      cream palette — user flagged it directly. Changed to a light mint
      card (`bg-genie-accent`) with dark text, matching every other
      section.

      **Correction #2 (same day, more important):** the first draft was
      wrong in two real ways, not just tone — (a) copy was over-specific to
      real estate ("AI for property businesses", "Built for real-estate
      teams") when Genie is a general document-intake/knowledge-base tool
      that happens to be used for property listings at C21 — property is
      one example of what you can upload, not the product's definition;
      (b) the hero mock **fabricated a capability Genie doesn't have** — it
      showed a user asking a property question and getting search results
      back, but this ingest assistant has **no search** (search-and-answer
      belongs to the separate `c21-property-chatbot` system — see
      `reference-org-chatbot-map.md`). User caught this from the "property
      business" framing alone; the search-claim inaccuracy surfaced while
      fixing that, not as a separate report — worth scrutinizing landing-
      page copy this way going forward, since marketing copy for a still-
      generic tool is an easy place to accidentally overclaim.
      Fixed: badge now "A knowledge base built from whatever you upload";
      subheadline lists document types as examples, not the product
      identity; "Built for teams of any kind" (not real-estate); hero mock
      redesigned entirely — now shows a forwarded PDF getting classified
      ("Got it — classified as market research") and synced, matching what
      `handle_message`'s actual ingest+classify+sync flow does, not a
      search Q&A. Feature card "Natural-language property search" replaced
      with "Classifies as it goes" (the real, generic classification
      behavior — listing vs. news vs. contact — with property named as
      just one of three examples in the body copy).
      Verified end-to-end in production after each round:
      `https://genie.infiniduo.com/` loads correctly, "Sign in" reaches the
      real login page.
- [ ] **Report-generation rework queued 2026-09-10** (c21-leasing website, +
      Slack/Teams if feasible) — this repo's `src/nodes/report_generator/`
      (orphaned since `/api/chat/report` was removed) is a reference/
      starting point only, not a working feature to just re-wire. Full plan
      queued in `c21-leasing`'s CLAUDE.md "Pending" section — check there
      first, this repo is not the primary owner of that work.
- [ ] **Wire PDF image extraction to Odoo product photos** (requested 2026-09-03, not started).
      `ocr.py`'s `_extract_images_from_pdf()` already pulls embedded images via PyMuPDF and
      uploads them to blob (`state.ocr.image_urls`) — but that's a dead end today, nothing
      downstream reads `image_urls` or uploads to Odoo. Manually proved the concept works for
      a 2-unit pitching deck (Connaught Marina): extracted per-page with PyMuPDF, verified
      complete against `pdfimages -list`, mapped photos to the correct unit by page number,
      uploaded as `product.image` + set page-1 cover as `image_1920` main thumbnail. To build
      for real: track page numbers through extraction (current blob upload loses them), map
      pages → unit via the same floor/unit boundaries the extractor already detects, and add
      this as a step in (or right after) `odoo_sync.py` so it runs on every future document,
      not just this one-off. See Session Summary below for full detail.

---

## Session Summary — 2026-09-13: Teams Channel Verified End-to-End, Committed, Bot Framework Credentials Fixed, Pitching-Deck Dedup Bug Found & Fixed, Deployed

### What happened
Started from "is this fixed?" against a screenshot of a Teams conversation with "C21
Document Assistant" processing a PDF. This repo's own docs had **zero** mention of Teams as
a channel, so this began as an audit — turned into finding and fixing two real bugs plus
closing a documentation/commit gap, verified against live Teams tests, Odoo, and the BAS
vector index.

### Finding 1 — Teams integration was real but undocumented/uncommitted
`api/routes/teams.py`, `src/utils/teams_notify.py`, `src/utils/teams_conversations.py`,
`teams-app-package/` mirror the WhatsApp/Slack architecture properly (Bot Framework
`CloudAdapter` auth, channel-agnostic `handle_message()`, async proactive-message notify via
`channel_notify.py`). Confirmed via Kudu that this had already been deployed out-of-band
(manually copied to wwwroot / the Function App's packaged zip) since at least 2026-09-12, but
was never `git commit`ed and never documented. This is a **different bot** from `bas-stacks`'
"C21net Property AI Agent (ALT)" Teams agent (property search, `supportsFiles: false`,
unrelated app registration) — see memory `reference-org-chatbot-map.md`.

### Finding 2 — Teams completion notify was silently failing (root cause found and fixed)
A live test's attachment resolved correctly (`_download_attachment()`'s
`application/vnd.microsoft.teams.file.download.info` path handled a real SharePoint
`downloadUrl` fine — the "attachments empty" scenario from the original 2026-09-12
diagnostic did not reproduce for this sharing method) and the pipeline completed
successfully (verified: Odoo updated, BAS index updated) — but **no completion message ever
reached Teams**. Root cause: `MICROSOFT_APP_ID`/`MICROSOFT_APP_PASSWORD`/
`MICROSOFT_APP_TENANT_ID` existed on the App Service (`.env` copy) but were **never set on
the Function App** (`c21net-bas-func-doc-pipeline-ea-prod`) — and `job_queue.py`'s async
notify (`channel_notify.py` → `teams_notify.py`) runs in the **Function App**, not the App
Service, so `_get_token()` always returned `None` and `send_teams()` failed silently (no
exception, no log line). Fixed by adding those three app settings to the Function App
(`az functionapp config appsettings set`). **Re-tested and confirmed**: the exact same
document, resent, produced a real Teams completion reply this time
("✅ 處理完成：...Odoo 放盤管理已建立/更新 13 筆記錄...").
Lesson: when a channel needs credentials in **both** services (App Service inbound + Function
App outbound-async), a settings audit should check both explicitly — matching this file's
existing `.env`-vs-Azure-app-settings distinction elsewhere.

### Finding 3 — Odoo/BAS data verified accurate, but found a real pitching-deck dedup bug
Cross-checked the synced CKKCC pitching-deck data directly: Odoo's `x_c21_listing` records
had internally-consistent size/rent/mgmt-fee math (fee = size × $5.5/sqft on every record)
and matched the source PDF's rate table exactly; `properties-index` (BAS's vector DB) had the
same record with correct metadata and full OCR content — confirming
`src/utils/bas_index_sync.py`'s immediate-sync-on-ingest path (added 2026-09-12, previously
undocumented) works.

However: the source PDF's table listed **14 units** but only **13** Odoo records existed.
Root cause in `odoo_sync.py`: `_map_fields()`'s pitching-deck path computed
`x_c21_floor_unit = unit.get("floor") or unit.get("unit")` — an **OR**, not a join. Two units
on the same floor with different letters (here, "29/F" 29A and 29B) both resolved to the same
key ("29/F"), so 29B's write silently overwrote 29A's record. No data was actually lost this
time only because 29A and 29B happened to have identical size/rent/fee — a lucky coincidence,
not a safe outcome in general. Confirmed via `extractor.py`'s PITCHING_DECK prompt that
`floor` and `unit` are already extracted as separate fields (schema example:
`{"unit": "G07", "floor": "G/F", ...}`) — this was purely a dedup-key bug, not a missing
extraction capability.

**Fixed** (`fe29121`): joined `floor`+`unit` consistently in both `_map_fields()` (where the
value is stored) and `_sync_pitching_deck_units()` (where the same value is looked up for
dedup), matching the pattern `_sync_units()`/`_map_unit_fields()` already used for
`listing_list` documents. Added `tests/test_odoo_sync_floor_unit.py` (odoo_sync.py had zero
prior test coverage). Full suite: 52 passed, same 4 pre-existing `test_nodes_ocr.py` failures
(unrelated import-path issue, predates this session).

**No data cleanup needed for the existing merged "29/F" record** — its values are accurate
for a coincidentally-identical pair of units. Only becomes stale if this exact document is
ever reprocessed post-fix: the new dedup key ("29/F 29A" / "29/F 29B") won't match the old
one ("29/F"), so a rerun would **create 2 new records** rather than update, leaving the old
merged record as a duplicate needing manual deletion at that point (same "Listing delete
doesn't cascade to Product/Unit Info" caveat as prior sessions' cleanups).

### Deployed this session
- Committed `498a17d` (Teams integration + channel-neutral reply text + `bas_index_sync.py`)
  and `fe29121` (floor/unit dedup fix + test) — previously all of this was either uncommitted
  local work or already-live-but-undocumented code.
- Added `MICROSOFT_APP_ID`/`MICROSOFT_APP_PASSWORD`/`MICROSOFT_APP_TENANT_ID` to the Function
  App's app settings (values copied from the App Service's `.env`, which already had them).
- Ran `./deploy.sh --all` to ship the floor/unit dedup fix to both services.

### Verified end-to-end (2026-09-13, real Teams tests, not simulated)
- Teams file-share attachment (SharePoint card) → OCR → classify → extract → Odoo sync →
  BAS vector index sync → **Teams completion notification received by the user** — full round
  trip confirmed working.
- Odoo data spot-checked field-by-field against the source PDF: accurate.
- `properties-index` document spot-checked directly via Search REST API: accurate, matches
  Odoo.

---

## Session Summary — 2026-09-03 (later): Reprocessing Overwrites Manual Edits + Duplicate Gallery Photos (found via a live Slack rerun test, fixed, deployed)

### What happened
Continuation of the same day's Connaught Marina test case (see the Session Summary directly below this one). After that session's fixes were deployed and the Odoo-side data was manually cleaned up (listing names shortened to "Connaught Marina 干諾中心 1/F"/"2/F", building link corrected — done from the `c21net.odoo.com` project, see its CLAUDE.md Decision 16), the exact same source PDF was deliberately re-sent through the **"Document Assistant" Slack bot** (this project's n8n-routed Slack channel — not to be confused with the separate **"C21 Property Chatbot"** Slack app, which lives in the unrelated `c21-property-chatbot` project and only does RAG-style Q&A via `/api/v1/chat`, no document ingestion) to verify the earlier fixes held under a real rerun.

The building-dedup fix (root cause #4 below) **held** — the rerun correctly resolved back to the same existing building. But two further bugs surfaced that the earlier session's fix didn't cover:

### Root causes
6. **Every UPDATE unconditionally overwrote `x_name` and `x_c21_status`.** The vals dict built by `_map_fields()`/`_map_unit_fields()` always includes a freshly-rebuilt `x_name` and a hardcoded `x_c21_status: "active"`, with no distinction between create and update. A rerun of the same PDF reverted the manually-shortened listing name back to the verbose auto-generated form (`"Connaught Marina 干諾中心 1/F 1/F樓 (Fitted 附設裝修)"`), and would silently un-archive any listing staff had marked 撤盤/已租出 in Odoo — undoing the Odoo-side archive-on-withdraw automation built the same day.
7. **`_sync_photos()`'s gallery sync had no dedup.** Every rerun re-extracted every embedded PDF image and unconditionally called `product.image.create()` for each, with no check for "already synced this page." Confirmed live: rerunning the same 2-unit PDF doubled the gallery image count on both products (5→10, 6→12).

### Fixes applied (commit `2e0f432`, deployed to `c21net-bas-api-doc-pipeline-ea-prod` only — no Function App code touched this round)
- New `_strip_manual_fields(vals)` helper strips `x_name`/`x_c21_status` from the write payload; applied at all 4 places the code writes to an *existing* `x_c21_listing` (`_sync_units`, `_sync_pitching_deck_units`, both update-paths in `_create_or_update`). Both fields are now only ever set on `create`, never on `write`.
- `_sync_photos()`: before creating a product's gallery images, now deletes that product's previously auto-synced set first (matched by the pipeline's own `"p<page> 圖片 <n>"` naming convention — staff-curated images use different names and are left untouched), making reruns idempotent instead of additive.
- Verified channel-agnostic: `odoo_sync` is a single shared LangGraph node for both WhatsApp and Slack (confirmed via `graph.py` — no per-channel branching), so this fix applies identically to both without any WhatsApp-specific handling needed.
- Test suite: 47 passed / 7 pre-existing failures (unrelated `blob.py`/`ocr.py` import-path issues, confirmed via `git stash` to predate this change) — no new failures introduced.

### Odoo data cleanup performed (data-only, no code)
Re-fixed listing 122/123 and product 56/57 names back to the clean short form after the rerun test reverted them; deleted the 11 duplicate gallery `product.image` records the rerun created (ids 37–47), keeping the original clean set (ids 26–36).

---

## Session Summary — 2026-09-03: Odoo API Key Renewal + Pitching-Deck Multi-Unit Sync Bugs (found, fixed, deployed)

### What happened
Started from a stale `ODOO_API_KEY` (WhatsApp pipeline was failing with "Odoo authentication
failed"). Renewed the key (reused the still-valid key from the `c21net.odoo.com` project's
`check_auth.py`) and updated it in this repo's `.env`, `odoo-bas-sync/local.settings.json`, and
the production Function App's app settings. While verifying the fix by reprocessing a real
document (`Connaught Marina - leasing particulars (2026)_260902_170013.pdf`, a 2-unit pitching
deck), found the sync was silently dropping data and, on a later rerun, creating duplicate Odoo
records — five separate bugs, all in `src/nodes/odoo_sync.py` / `src/nodes/extractor.py`.

### Root causes
1. **Multi-unit pitching decks only synced the first unit.** `_map_fields()`'s single-record path
   did `unit = raw["available_units"][0]` — any document classified `pitching_deck` (not just
   `listing_list`) with more than one unit silently dropped every unit after the first. This is
   how the 2/F unit went missing on the first sync.
2. **`PITCHING_DECK` extraction prompt never asked for spec/fee fields that `odoo_sync.py` already
   had mapping code for.** `electrical`, `drainage`, `aircon`, `water_supply`, `handover`,
   `gas_supply` were mapped from `raw[...]` in code, but the prompt (`extractor.py`) never
   included those keys — always blank for pitching-deck docs. Same for total 管理費 (never
   computed from psf × size) and 差餉/地租 (no extraction path at all) and 樓底高度 (brand new Odoo
   field, no extraction support).
3. **Dedup-key mismatch (introduced and fixed same session) in the new multi-unit sync path.**
   The fix for bug #1 (`_sync_pitching_deck_units`) computed its dedup search key by joining
   `unit.get("floor")` + `unit.get("unit")`, but `_map_fields()` actually stores only
   `unit.get("floor") or unit.get("unit")` (OR, not joined) in `x_c21_floor_unit`. When one
   extraction run returned two different "shapes" for the same physical unit (one with just
   `floor`, one with `floor` + a `unit` string carrying fit-out text), the second shape's search
   key never matched the first's stored value → created a duplicate listing instead of updating.
4. **Building dedup broken by a manual Odoo edit.** `_get_or_create_building()`'s fallback search
   was `x_name ilike <AI-extracted building name>` — one-directional substring match. A user
   edit in Odoo split "Connaught Marina 干諾中心" into `x_name="干諾中心"` +
   `x_name_en="Connaught Marina"`; the AI's full extracted name no longer appears as a substring
   of the (now shorter) `x_name`, so a duplicate Building record got created and both listings got
   silently re-pointed to it on the next sync.
5. **Duplicate-record IDs in the WhatsApp completion message.** Both multi-unit sync loops
   (`_sync_units`, `_sync_pitching_deck_units`) appended every processed unit's resulting ID to
   the returned list unconditionally — when bug #3's extraction "shapes" both correctly matched
   the same existing record (after the dedup fix), the same ID got appended twice, so the WhatsApp
   reply said "4 筆記錄 (ID: 122,123,122,123)" for what was really 2 records.

### Fixes applied (all deployed to both `c21net-bas-api-doc-pipeline-ea-prod` App Service AND
`c21net-bas-func-doc-pipeline-ea-prod` Function App — see [[feedback-deploy-discipline]])
- `odoo_sync.py`: new `_sync_pitching_deck_units()` — routes any `pitching_deck` doc with >1
  `available_units` through a per-unit create/update loop (reusing `_map_fields(unit=...)`
  rather than `_map_unit_fields`, since pitching decks use the `size_sqft`/`rent_monthly` key
  names, not `listing_list`'s `size`/`rent`).
- `_map_fields()`: new optional `unit` param (defaults to `available_units[0]` — unchanged
  behavior for single-unit docs); maps `unit["rates_quarterly"]`/`unit["govt_rent_quarterly"]` →
  `x_c21_rates`/`x_c21_govt_rent`; auto-computes `x_c21_mgmt_fee = psf × size_sqft` (deterministic,
  no LLM needed); maps new `ceiling_height` key → `x_c21_ceiling_height`.
- `extractor.py`: `PITCHING_DECK` prompt now asks for `electrical`, `drainage`, `water_supply`,
  `aircon`, `gas_supply`, `handover`, `ceiling_height` (top-level) and `rates_quarterly` /
  `govt_rent_quarterly` (per-unit, inside `available_units[]`), with extraction-rule hints for
  each (Chinese label → key mapping).
- `_sync_pitching_deck_units()` dedup key fixed to match `_map_fields()`'s storage exactly
  (`unit.get("floor") or unit.get("unit")`, not joined).
- `_get_or_create_building()`: added two more fallback searches before giving up and creating a
  new building — `x_name_en ilike <name>`, then a Python-side address-overlap check
  (`_address_overlap`, already used for the ALS-match-rejection case) against every building's
  `x_address`. Address is a much more stable identifier than a free-text name that can be
  manually edited.
- `_sync_units()` and `_sync_pitching_deck_units()`: both now dedup the returned ID list
  (`if unit_id not in ids: ids.append(...)`) so the WhatsApp completion message reports the true
  record count.
- Odoo Studio: added `x_c21_ceiling_height` (listing) → `x_c21_unit_info.x_c21_ceiling_height` →
  `product.template.x_c21_ceiling_height_display` (related field), wired into the existing
  `ir.actions.server` #1142 listing→product sync, and registered as a `trigger_field_ids` entry on
  `base.automation` #5 (new custom fields are NOT auto-included in that trigger list — easy to
  miss; a write to a field not in it silently does nothing).

### Known remaining issues (not fixed this session)
- **Rent extraction is unreliable for this specific document** — the extraction LLM
  (`qwen/qwen-2.5-72b-instruct` via OpenRouter, see `src/utils/llm.py`) has tripled the monthly
  rent (e.g. $53,430 → $160,290) on *every* rerun of this PDF, consistently 3×. Root cause is in
  the model's reasoning, not the code — no deterministic multiplier exists anywhere in the
  pipeline. A cheap guard worth adding: cross-check `rent_net ≈ size_sqft × rent_per_sqft` when
  both are extracted and flag mismatches for review instead of trusting the LLM's arithmetic.
  Model swap was considered but deferred — some OpenRouter models are blocked from Hong Kong,
  needs checking which ones are actually reachable before picking a replacement.
- **`x_c21_date_received` (收到日期) still doesn't populate for WhatsApp-ingested files.**
  `_extract_date()` expects an 8-digit `YYYYMMDD` run in the filename; actual WhatsApp/Twilio
  filenames use `YYMMDD_HHMMSS` (e.g. `..._260902_170013.pdf`), which never matches.
- **No automated image extraction yet.** Manually verified (via PyMuPDF, cross-checked against
  `pdfimages -list`) that all embedded photos/floor plans in a pitching deck can be reliably
  extracted and mapped to the right unit's product by page number. Not yet built as a pipeline
  node — remains a manual one-off process for now.

### Odoo data cleanup performed (data-only, no code)
Duplicate Building 34 (created by bug #4) and duplicate Listings 124/125 + their auto-generated
Products 58/59 + Unit Info 50/51 (created by bug #3, before its fix was deployed) were deleted;
Listings 122/123 were re-pointed back to the correct Building 33. Verified via read-back that
exactly 2 listings remain for Connaught Marina, both linked to one building, with no orphaned
Unit Info/Product records left behind (deleting a Listing does **not** cascade-delete its linked
Unit Info/Product — no automation handles `unlink`, only `on_write`/`on_create_or_write` — so any
future manual listing deletion needs the same manual cleanup of its Product/Unit Info).

Separately confirmed **not a regression**: 44 of 47 total `product.template` records are archived
(`active=False`) with `create_date` predating this session (some from 2026-05) — pre-existing
draft/test catalog state, unrelated to anything fixed or deployed this session.

---

## Session Summary — 2026-08-04: Knowledge Article Hallucination Bug (found, fixed, deployed, backfilled)

### What happened
A WhatsApp forward (bus-ad image + short caption + `share.google` link) produced a fabricated
Odoo Knowledge article about a "中環豪宅成交" (Central luxury sale) — completely unrelated to the
real source (a KKday × 永東巴士 coach-ticket promo). Root-caused via direct Odoo XML-RPC
inspection (`documents.document` + `knowledge.article` `read`) and live browsing of the actual
`share.google` link.

### Root causes (three independent bugs, all in the news/knowledge path — NOT the main
`extractor.py` NEWS prompt, which is a separate, unaffected code path)
1. **`src/nodes/knowledge_writer.py` `ARTICLE_PROMPT`** — the OUTPUT FORMAT example embedded
   *literal* placeholder values (`29/6/2026`, `Unit 11/12`) instead of bracketed placeholders.
   With near-empty source text, Qwen copied the example values verbatim into the live article
   instead of leaving the table empty. No "insufficient content" escape hatch existed at all
   (unlike `extractor.py`'s LISTING prompt, which already has one).
2. **`src/utils/url_fetcher.py` `resolve_redirect()`** used an HTTP **HEAD** request — `share.google`
   only completes its 2-hop redirect chain to the real article on **GET**; HEAD dead-ends on a
   Google interstitial page. Confirmed by direct testing against the real failing URL.
3. **`TAVILY_API_KEY` was never configured** for this repo (not in `.env`, not as an Azure app
   setting on either service) — `enrich_with_url_content()` had been a silent no-op in production
   since it was written. Fix #2 alone would have done nothing without this.
4. (Found during fix #3) Even with a working key, **Tavily's `/extract` API got bot-walled by
   `etnet.com.hk`** — a plain `httpx` GET with a normal desktop User-Agent fetched the real
   article fine, but Tavily's crawler got an "idle, please reload" placeholder page instead.
5. (Found while verifying the regenerated articles) **URL/link regexes in both `url_fetcher.py`
   and `knowledge_writer.py`** used `\S+`/`[^\s<>"')]+`, which also matches CJK characters glued
   directly onto a URL with no separator (e.g. `http://on.cc東網` — a source citation like
   "on.cc東網", not a real link at all). This produced broken/garbage `<a href>` links in
   generated articles. Fixed by restricting both regexes to printable-ASCII (`[!-~]+`).

### Fixes applied (all deployed to both `c21net-bas-api-doc-pipeline-ea-prod` App Service AND
`c21net-bas-func-doc-pipeline-ea-prod` Function App — pipeline code needs both, per
[[feedback-deploy-discipline]])
- `knowledge_writer.py`: bracketed placeholders in `ARTICLE_PROMPT`; hard guard (skip LLM call
  entirely if source text < 60 chars); LLM-level `{"insufficient_content": true}` escape hatch;
  printable-ASCII-only link regex.
- `knowledge_sync.py` / `job_queue.py`: new `"skipped"` odoo_sync_status path with a clear
  WhatsApp reply ("⚠️ 內容不足，未能生成知識文章...") instead of silent fabrication.
- `url_fetcher.py`: `resolve_redirect()` now GETs (not HEAD); **primary content-fetch path is now
  a direct `httpx` GET + `<article>`-tag regex extraction**, falling back to Tavily only if that
  finds nothing — more reliable than Tavily alone and avoids the etnet bot-wall; printable-ASCII
  URL-extraction regex.
- `TAVILY_API_KEY` added to both services — **reused from `c21-property-chatbot`'s existing key**
  (shared free-tier quota, not a dedicated key — see memory `project-tavily-key-shared.md` for the
  tradeoff and why).

### Odoo data backfill (data-only, no code — full scan of the "📊 Marketing News" Knowledge folder)
Found the bug had fired at least **5 times** before this session caught it (not just the 1
reported). Per-article remediation (judgment call each time — grepping for the literal
`29/6/2026`/`Unit 11/12` strings alone gives false positives, see article 53 below):
- **69, 70** — fully fabricated, wrong topic entirely → archived (Odoo Knowledge trash:
  `active=False, to_delete=True` together, or Odoo silently no-ops the trash write).
- **61, 62, 63** — all three trace to the *same* `share.google` link (one real event reprocessed
  3x: 61 = LLM JSON parse failed → empty stub, 62/63 = two different fully-fabricated fake
  stories). Archived all three, replaced with **one** correct article (73) after resolving the
  real source (元朗虹方 property portfolio → mortgagee sale).
- **54, 59, 60** — real, accurate article content, but a nonsensical "成交日期/成交單位" transaction
  table bolted onto stories that aren't about a specific unit transaction (a tender, a
  market-trend piece, a quarterly overview). Surgically removed just the bad table (content
  otherwise untouched).
- **55** — accurate transaction data throughout except a fabricated date; corrected to the date
  the source actually implies ("昨日" relative to the article's dateline).
- **64** — accurate content including a real quote; only the date field was fabricated (no
  reliable date to infer this time, unlike 55) → removed just that row.
- **53** — flagged by the naive grep (contains `29/6/2026`+`Unit 11/12`) but verified 100%
  accurate against the real source flyer — a genuine coincidence, left untouched. This is
  probably where the broken prompt's placeholder example values originally came from.

### Deploy incident (self-inflicted, cost ~1 hour) — see [[feedback-deploy-discipline]]
Chained `./deploy.sh` immediately followed by `./deploy.sh --func` (which *also* redeploys the
App Service first) — the second zipdeploy's SCM container restart hit the first deploy's still-
finishing VFS upload, corrupting wwwroot and taking the App Service down (503, container exit
code 1) for several minutes. This is exactly the scenario the **"NEVER chain `./deploy.sh`+`--func`
back-to-back"** rule two paragraphs below already warns about — re-confirmed the hard way.
Recovery: clean re-run of `./deploy.sh` alone fixed it. Separately (unrelated to the chaining
mistake), the remote Oryx build for the Function App **hung twice** on
`"Requesting metadata for platform python from external SDK provider"` — confirmed via Kudu's
`/deployments/{id}/log` endpoint showing no progress for 13+ minutes, not just "slow." Recovery
pattern each time: `az functionapp restart` to clear the stuck build, then retry
`./deploy.sh --func-only`. Lesson: don't trust `func azure functionapp publish`'s own exit code
or "Remote build succeeded!" message at face value — it has given a false "done" signal (CLI gave
up polling early) at least once this session. Always independently verify via Kudu's
`/api/deployments` (`complete: true`, `active: true`) AND by downloading the actual deployed
package (`/api/vfs/data/SitePackages/{name}.zip` for the Function App — **not** `/site/wwwroot`,
which is irrelevant for Linux Consumption Python Function Apps; they run from a packaged zip
under `/home/data/SitePackages`) and grepping it for the expected code.

---

## Session Summary — 2026-07-30/31: Odoo→BAS Sync + Standalone Property Chatbot

Two new standalone repos built and deployed, both live in production and
pushed to GitHub. Neither shares code with this repo — only external data
(Odoo, BAS's Azure Search index). Also fixed a gap in this repo's own Odoo
instance and committed a large backlog of already-deployed-but-uncommitted
work (the ingest-only pivot itself had never been git-committed until now).

### 1. Odoo Automated Action (in this repo's Odoo instance, not a code change)
Added a `base.automation` + `ir.actions.server` on `x_c21_listing` that
auto-flips `x_c21_published` back to `False` whenever a human edits a
listing's business fields directly in Odoo's UI — closes the last gap in the
"Odoo is source of truth, trust-AI" sync design. Non-obvious gotcha: an
`object_write` server action needs BOTH `update_field_id` AND `update_path`
set, or it silently no-ops — Odoo's own UI sets both together via onchange,
but the API does not auto-populate `update_path` from `update_field_id`.

### 2. `x_c21_doc_url` field — closed end-to-end, committed (`4975b3a`)
Added `x_c21_doc_url` (char) on `x_c21_listing`; `odoo_sync.py`'s
`_map_fields()`/`_map_unit_fields()` now write it (previously the Documents
share URL was only embedded inside `x_c21_notes` HTML, never a clean field).
Backfilled 45 existing listings by regex-extracting the URL out of their old
HTML notes. Verified live: `properties-index`'s `odoo-listing-3` now has a
real `sourceWebUrl`, meaning BAS's Teams bot can render a clickable document
button for listings synced from here on.

### 3. `odoo-bas-sync` (new repo: `github.com/lojul/odoo-bas-sync`)
Daily sync job: reads Odoo `x_c21_listing` records where
`x_c21_published=False`, embeds via Azure OpenAI, upserts into BAS's
`properties-index`, flips the flag back to `True`. Deployed as Function App
`c21net-bas-func-odoo-sync-ea-prod` (own managed identity, RBAC-granted on
BAS's OpenAI + Search resources). Verified end-to-end on real production
data. Only 3 of ~46 pending listings synced so far — the daily 18:00 UTC
timer will pick up the rest automatically.

### 4. `c21-property-chatbot` (new repo: `github.com/lojul/c21-property-chatbot`)
Standalone, channel-agnostic internal chatbot for C21 **staff** (not
customers) — built because BAS's own Teams bot gates every message behind a
lead-qualification funnel and felt much less capable than this org's old,
now-deleted `chatbot.py`.

- Channel-agnostic API: `POST /api/v1/chat {channel, conversation_id,
  message}` — any channel adapter calls this same contract, no
  channel-specific logic mixed into the core.
- Agent: LangGraph `create_react_agent`, LLM = `moonshotai/kimi-k2` via
  OpenRouter — chosen over reasoning variants (`k3`, `k2.6+`) which are
  ~50-90x more expensive and can silently return empty content if
  `max_tokens` is too low for their hidden reasoning pass.
- 5 tools, all real and verified against production data: `search_properties`
  (hybrid+semantic search on BAS's `properties-index`, read-only),
  `create_crm_lead` (writes Odoo `crm.lead`), `search_contacts` (real-time
  Odoo `res.partner` lookup), `search_knowledge` (real-time Odoo
  `knowledge.article` lookup), `web_search` (Tavily, for general HK
  commercial property market questions the internal data can't answer).
- Daily usage limiting: per-user cap (default 20/day) + a global backstop cap
  (default 300/day) via Azure Table Storage — the global cap specifically
  guards against the channel API key ever leaking (a per-user cap alone is
  trivially bypassed by inventing new fake user IDs).
- Design decisions (user-specified): property search accuracy is the primary
  job, never gated behind budget/district/timeline questions; CRM lead
  logging is a secondary, optional add-on, only on explicit request; the
  chatbot talks to **staff describing a customer**, never to the customer
  directly (never 2nd-person "you"/"您" toward the lead).
- Deployed: App Service `c21net-bas-api-property-chatbot-ea-prod` (core API)
  + Function App `c21net-bas-func-chatbot-slack-ea-prod` (Slack adapter),
  both in RG `c21net-bas-property-chatbot-ea-prod`. Slack App "C21 Property
  Chatbot" is registered and installed workspace-wide (visible under Agents
  and apps for every member, no per-person setup). **2026-09-10: found
  completely broken** (every request 500'd — `langchain.agents.create_agent`
  auto-computed a `max_tokens` that exceeded OpenRouter's Novita provider
  cap for kimi-k2) since the `ce0bac5` migration commit, unused/unnoticed
  until then; fixed (`max_tokens` capped explicitly) and **confirmed live
  and replying correctly end-to-end in Slack**, including real
  `search_properties` results. Has a real daily cap (20/user, 300 global,
  see `core/rate_limit.py`) — document-processor's own assistant does not.
  See memory `reference-org-chatbot-map.md` for the full org picture.

### Reusable gotchas found (apply to any future Azure work in this org)
1. **Azure Storage Queue messages need `TextBase64EncodePolicy()`** when sent
   via the SDK (`azure-storage-queue`), or the Functions host silently fails
   to invoke the queue-triggered function — no exception anywhere, the
   message just poison-queues after 5 retries. Already done correctly in
   `src/utils/job_queue.py` — any new queue-based Function App should copy
   that pattern from the start, not rediscover it.
2. **A new Storage Queue must be created explicitly** before first use
   (`queue_client.create_queue()`) — it does not auto-create on
   `send_message()`.
3. **Slack's "Socket Mode" silently overrides the Request URL** — when
   enabled, events are delivered over a WebSocket instead of HTTP POST to
   the configured webhook. The webhook's one-time URL-verification check
   still passes (a separate mechanism), masking the problem — real events
   just never arrive. Must be disabled for a standard Events API webhook to
   receive anything.
4. **Slack's `X-Slack-Retry-Num` header is NOT a reliable dedup signal** —
   tested live, a duplicate delivery got through with no retry header set at
   all. The robust fix is content-based: Slack's `event_id` (present on
   every delivery, retries included) + an atomic Table Storage
   `create_entity()` insert as the idempotency lock — `ResourceExistsError`
   means "already processed, skip."
5. **App Service zipdeploy needs `Content-Type: application/zip`**, not
   `application/json` — the deploy recipe documented later in this file
   (under "Deploy" in the FastAPI Backend section) uses `application/json`
   and failed here with a cryptic `400 Deployment Failed. Unexpected
   character... value: P` (the parser choking on the zip's own `PK` magic
   bytes) when tried against the new property-chatbot App Service. Worth
   re-testing on this repo's own App Service next deploy — that recipe may
   have always been subtly wrong.
6. **`az functionapp create --plan`/`--storage-account` accept full resource
   IDs for cross-resource-group reuse** — confirmed working: reusing an
   existing plan/storage account from a different RG than the new
   Function App's own RG is fine, just pass the full ARM resource ID, not
   the bare name (which resolves relative to `--resource-group` and 404s).

### Architecture debt noted, not urgent — `src/nodes/assistant.py` channel mixing
Audited against the clean separation used in `c21-property-chatbot`
(channel-agnostic core API, thin per-channel adapters). Findings:

**Good, matches the pattern — no change needed:**
- `function_app.py`'s `pipeline_job_worker` — thin adapter, deserializes the
  queue message and calls `run_pipeline_job()`, no business logic itself.
- n8n's workflow config is entirely external to this repo — just a
  documented contract in, a notify webhook out.
- `api/routes/assistant.py` → `handle_message()` is a reasonably clean HTTP
  seam — auth, file resolution, then delegates.

**Tangled — inside `handle_message` itself (`src/nodes/assistant.py`):**
despite taking a generic `channel` parameter, channel-specific logic is woven
directly into the "core" agent rather than isolated in an adapter — e.g.
`if channel in ("whatsapp", "slack")` fast-paths that skip the normal agent
flow (justified by avoiding n8n's HTTP timeout — a transport limitation
leaking into agent logic), Slack mrkdwn link-unwrapping sitting inline in the
core function, and WhatsApp-only branches/fields threaded through
`contact_staff`, `log_property_inquiry`, `_dispatch_pipeline_async`.

**Cost:** adding a real second channel to this assistant (e.g. Teams for
document intake) would mean more conditionals inside `assistant.py`, not a
clean new adapter — the opposite of what `c21-property-chatbot` achieves.

**Suggested future refactor (not urgent — this is live and working, this is
architectural debt, not a bug):** extract the channel-conditional shortcuts
out of `handle_message` into the route/adapter layer
(`api/routes/assistant.py`) or a thin per-channel pre-processor, so
`handle_message` becomes genuinely channel-blind.

### Pending / next steps (as of 2026-07-31)

**Git status — all clean.** All three repos (`document-processor`,
`odoo-bas-sync`, `c21-property-chatbot`) are fully committed and pushed to
GitHub as of this writing.

**`odoo-bas-sync`:** only 3 of ~46 pending listings synced so far — the
daily 18:00 UTC timer will pick up the rest automatically, or trigger
`POST /api/sync` on `c21net-bas-func-odoo-sync-ea-prod` manually.

**`c21-property-chatbot`:**
- Slack Function App's slow cold-start ack (15-34s, sometimes triggering
  Slack retries) — root cause never diagnosed, only worked around via
  event_id-based dedup. Could still show up as a noticeable reply delay.
- No Application Insights configured on the core API App Service
  (`c21net-bas-api-property-chatbot-ea-prod`) — only the Function Apps have
  it. Add if this App Service ever needs debugging.
- Security follow-ups discussed, not yet done: rotate API keys periodically
  as good practice, and review who has Azure RBAC access to read App
  Settings on `c21net-bas-property-chatbot-ea-prod` (anyone with read access
  can see these secrets in plaintext via the Azure Portal).
- Slack queue polling interval (`host.json`, `MaxPollingInterval`) could be
  reduced for snappier replies — currently up to 1 minute added latency.

**This file vs. `document processor/CLAUDE.md` (parent directory, no git
repo of its own):** that outer file is a STALE duplicate — it still
describes the pre-pivot OneDrive/Streamlit/Next.js dashboard architecture
this file's own intro note (top of file) already marked removed on
2026-07-28. Worth reconciling or deleting that outer copy; not done as part
of this session since it wasn't the scope asked for.

---

## Graph 1: Document Processing

**File:** `src/graph.py` | **LangSmith Project:** `document-processor`

### Flow
```
__start__
    ↓
get_download_url (OneDrive via Microsoft Graph)
    ↓
run_ocr (Azure Document Intelligence + PyMuPDF image extraction)
    ↓
classify (OpenRouter Qwen 2.5)
    ↓
analyze (Pre-extraction document structure analysis)
    ↓
extract (OpenRouter Qwen 2.5)
    ↓
index (Azure AI Search + Azure OpenAI embeddings + Smart Merge)
    ↓
__end__
```

### Document Types & Extracted Fields
- **listing**: One property (building_name, address, size, rent, contact)
- **listing_list**: Multiple properties in a table (building info + units array)
- **pitching_deck**: Property marketing presentations (project_summary, available_units, location, key_features, design_team, contact)
- **news**: Article (title, date, source, summary, topics)
- **contact**: Business card (name, company, phone, email)

---

## Key Services

### Azure AI Search (verified live 2026-07-28)
- Endpoint: `c21net-bas-srch-ea-prod.search.windows.net` (NOT `aisearch-eastasia-basic` —
  that name is stale/wrong)
- Index: `property-intel-index` (`AZURE_SEARCH_INDEX` / `AZURE_SEARCH_INDEXES` in `.env`)
  — NOT `processed-documents`, which no longer exists as the live write target
- `content_vector`: **3072 dims**, HNSW/cosine, profile `default-profile`
- **This repo's pipeline does NOT write to this index at all** (see architecture note
  at top of file) — `graph.py` v2 routes everything to Odoo only. Confirmed remaining
  *readers*: `extractor.py fetch_examples()` (keyword search, few-shot examples,
  fails open) and `assistant.py check_listing_duplicate()` (single-doc dedup GET).
  `extractors/conversational.py _find_similar_documents()` imports from the now-deleted
  `src/nodes/indexer.py` — this is dead/broken code (silently fails open, never crashes,
  but should be cleaned up).
- **Deprecation in progress:** this index is being retired in favor of the separate BAS
  project's `properties-index` (same search service, different schema — see memory
  `project-odoo-to-bas-sync.md` for the gap analysis and migration plan).
- `c21net-intelligence-v2` / multi-index chatbot search: **removed**, no longer applies.

### Azure OpenAI
- Endpoint: `swedencentral.api.cognitive.microsoft.com`
- Embedding model: `text-embedding-3-large` (**3072 dimensions** — corrected 2026-07-28;
  was documented as `text-embedding-3-small`/1536 dims, which is stale. Confirmed via
  live App Service env var `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` and the index's actual
  `content_vector` field schema.)

### AI Classification/Extraction
- Provider: OpenRouter — `qwen/qwen-2.5-72b-instruct`
- Temperature: 0 (deterministic)
- Anti-hallucination prompts: return null for missing fields
- **LLM resilience (2026-07-05):** all pipeline LLM calls (classify/analyze/extract) go through
  `openrouter_chat()` in `src/utils/llm.py` — Qwen, retry once after 2s, then fall back to
  `deepseek/deepseek-chat`. Added after OpenRouter failed 3 ways in 2 days (502/504/400) and
  single blips degraded runs to UNKNOWN. Do NOT add raw `httpx.post` OpenRouter calls in nodes.
- **Extraction memory Phase 1 (2026-07-05):** `fetch_examples()` in extractor.py retrieves the
  2 most similar past extractions (same document_type) from Azure AI Search and injects them as
  few-shot examples before extracting. Fails open. Quality compounds as good extractions accumulate.
- **Listing names (2026-07-05):** extractor captures `listing_ref` (樓盤編號) + `headline`;
  `_build_listing_name()` in odoo_sync.py enriches short/generic names → "中環 商舖 #10978"
  instead of "中環". Teaser ads (IG/WhatsApp promos) often carry no address.

### OpenRouter Models — Hong Kong

**Working:** `qwen/qwen-2.5-72b-instruct`, `deepseek/deepseek-chat`, `meta-llama/llama-3.3-70b-instruct`, `mistralai/*`

**May not work:** `anthropic/claude-*`, `openai/gpt-*`, `google/gemini-*` (US company regional blocks)

---

## Graph 2: RAG Chatbot — REMOVED (verified 2026-07-28, historical section)

> `src/nodes/chatbot.py` no longer exists in this repo. `prop-chat` App Service was
> stopped 2026-07-27 (see memory `project-trim-status.md`), pending deletion. `/api/chat`
> and `/api/search` routes are not registered in `api/doc_pipeline_main.py`. Section kept
> for historical reference only — do not treat anything below as currently deployed.

**File:** `src/nodes/chatbot.py` (deleted) | **LangSmith Project:** `property-chatbot`

### Architecture
```
User Question → route_query → search (vector/web/hybrid) → build_context → call_llm → Answer
```

| Node | Purpose |
|------|---------|
| `route_query` | Determines search strategy |
| `search_documents` | Multi-index hybrid search (Azure AI Search) |
| `web_search` | Tavily web search for trends/news |
| `build_context` | Merges & formats results for LLM |
| `call_llm` | OpenRouter Llama 3.3 70B |

### Query Router
| Route | Keywords |
|-------|----------|
| `vector` | 出租, 寫字樓, office, district names |
| `web` | 趨勢, 市場, 新聞, forecast, 2024/2025/2026 |
| `hybrid` | 比較, compare, versus |

### Configuration
- LLM: `meta-llama/llama-3.3-70b-instruct`, temperature 0.5, max 2000 tokens
- Memory: `MemorySaver` (session-scoped; use `PostgresSaver` for persistent)
- Guardrail: ONLY Hong Kong commercial property questions

### Chatbot v2 — REMOVED (2026-07-05)
`chatbot_v2.py` was deleted. It was a June refactor preparing for a tool-calling agent, but the
WhatsApp assistant (`src/nodes/assistant.py`) already IS that agent, and v2 lacked multi-index
search. If dashboard chat should become agentic, expose the existing assistant
(`channel="dashboard"` is already supported) — do not rebuild a parallel chatbot.

---

## Report Generator

**Files:** `src/nodes/report_generator/` | Triggered by: Chat tab "生成報告 PDF" button in Next.js dashboard

Uses **chat conversation sources** (not a separate search) to generate PDF reports.

```
router.py → validator.py → aggregator.py → statistics.py → pdf_generator.py → main.py
```

Entry point: `generate_report_from_sources(sources, district, district_en, report_type)`

- Format: A4, professional, C21 branding, bilingual (Chinese + English)
- Types: Rent Analysis, Availability
- Dependencies: `fpdf2` (in requirements.txt), `jinja2`
- `pdf_bytes` is `bytearray` — must cast to `bytes` in FastAPI: `Response(content=bytes(result.report.pdf_bytes), ...)`

**Known issue:** Chinese font may not render correctly in PDF reports (debug `_get_chinese_font()` in `pdf_generator.py`).

---

## Next.js Dashboard (Primary UI)

- **Local:** `cd nextjs-dashboard && npm run dev` → http://localhost:3000
- **Production:** https://wonderful-flower-006019c00.7.azurestaticapps.net/ (Azure Static Web Apps — free tier)
- **GitHub:** https://github.com/lojul/property-intelligence-dashboard (separate repo, `main` branch)
- **Deploy:** Push to `main` → GitHub Actions auto-builds and deploys (workflow: `.github/workflows/azure-static-web-apps-wonderful-flower-006019c00.yml`)
- **Build env vars:** `NEXT_PUBLIC_API_URL` set in the workflow file (build-time, not runtime)
- **Auth:** JWT login via `POST /api/auth/login`; token stored in `localStorage`, sent as `Bearer` on every API call

### Routes
| Route | Label | Notes |
|-------|-------|-------|
| `/chat` | Chat | RAG chatbot, Llama 3.3 70B label, "生成報告 PDF" button |
| `/search` | Keyword Search | Direct keyword search, no AI |
| `/admin/ingest` | Ingest | Drop PDF/Word/PPT/JPG/PNG; AI triages each file then upload to OneDrive /In |
| `/admin/process` | Processing | Two tabs: Recent (LangSmith 72h) + History (Azure Table Storage, all time) |
| `/admin/vector` | Vector DB | Azure AI Search documents |
| `/admin/settings` | Settings | (placeholder) |

### Chat UI Details
- Bilingual (Chinese/English) — responds in same language as query
- Model label: "Llama 3.3 70B" shown dimmed in chat header
- "生成報告 PDF" button: only visible when conversation has listing/listing_list sources
- Uses `allSources` (collected across all completed assistant messages) — not just last response
- Clicking "生成報告 PDF" calls `generateReport(allSources)` → downloads PDF blob

### Deploy
```bash
cd nextjs-dashboard
npm run build   # outputs ./out (static export)
SWA_TOKEN=$(az staticwebapp secrets list \
  --name c21net-bas-web-prop-intel-dashboard-ea-prod \
  --resource-group c21net-bas-document-processor-ea-prod \
  --query "properties.apiKey" -o tsv)
npx @azure/static-web-apps-cli deploy ./out \
  --deployment-token "$SWA_TOKEN" --env production
```

### Environment Variables
Set at build time in `nextjs-dashboard/.env.local` (not committed):
```
NEXT_PUBLIC_PIPELINE_API_URL=https://c21net-bas-api-doc-pipeline-ea-prod.azurewebsites.net
NEXT_PUBLIC_CHAT_API_URL=https://c21net-bas-api-prop-chat-ea-prod.azurewebsites.net
```

---

## FastAPI Backend (Split into Two Services)

The monolithic API is split into two named App Services:

| Service | Entrypoint | URL | Routes |
|---------|-----------|-----|--------|
| `c21net-bas-api-doc-pipeline-ea-prod` | `api/doc_pipeline_main.py` | `https://c21net-bas-api-doc-pipeline-ea-prod.azurewebsites.net` | `admin`, `assistant` (only two routers registered — verified 2026-07-28) |
| `c21net-bas-api-prop-chat-ea-prod` | `api/prop_chat_main.py` (file no longer exists) | `https://c21net-bas-api-prop-chat-ea-prod.azurewebsites.net` | **STOPPED 2026-07-27**, pending deletion — see memory `project-trim-status.md` |

- **Resource group:** `c21net-bas-document-processor-ea-prod` | **Subscription:** `c21net-business-automation-stack`
- Old monolith `c21net-bas-api-prop-intel-core-ea-prod` was deleted (verified gone 2026-07-05)
- **App Service Plan:** `c21net-bas-asp-ea-prod` (B1, Linux, Python 3.12)
- **Deploy dir:** `/private/tmp/api_deploy_dir/` — staged files live here; do NOT clean between deploys

### Deploy Workflow — USE `./deploy.sh` (added 2026-07-04)

```bash
cd langgraph
./deploy.sh          # doc-pipeline App Service
./deploy.sh --chat   # + prop-chat App Service
./deploy.sh --func   # + Function App
./deploy.sh --all    # everything
```

The script does the full sequence with built-in guards: stage → zip (size + freshness checks) →
zipdeploy → wait for the NEW deployment id (avoids race with the previous deploy) → copy source
to wwwroot → restart → health poll. Do NOT hand-run the steps below anymore — manual deploys
caused stale-zip incidents twice on 2026-07-04.

**Function App:** `.funcignore` (excludes `.venv/`, `tests/`, etc.) is REQUIRED. Without it,
`func publish` uploads ~918MB and silently deploys stale code.

### Manual steps (reference only — what deploy.sh automates)

`az webapp deploy --type zip` and `az webapp deployment source config-zip` both drop the connection. Use the Kudu REST API directly:

```bash
# 1. Sync source files to deploy dir (--delete removes stale files)
cd "/Users/kincheonglau/Active Projects/document processor/langgraph"
rsync -a --delete src/ /private/tmp/api_deploy_dir/src/
rsync -a --delete api/ /private/tmp/api_deploy_dir/api/
cp requirements-api.txt /private/tmp/api_deploy_dir/requirements.txt

# 2. Clean pycache and zip — IMPORTANT: separate rm and zip, do NOT chain with &&
cd /private/tmp/api_deploy_dir
find . -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
rm -f /private/tmp/api-deploy.zip
zip -r /private/tmp/api-deploy.zip . -x "*.DS_Store"

# 3. Verify new entrypoints are in the zip before deploying
unzip -l /private/tmp/api-deploy.zip | grep -E "doc_pipeline|prop_chat|requirements.txt"

# 4. Get bearer token
TOKEN=$(az account get-access-token --resource "https://management.azure.com/" --query accessToken -o tsv)

# 5. Deploy to Pipeline API
# IMPORTANT: --http1.1 is required. Without it, HTTP/2 framing causes connection drop (HTTP 000).
curl --http1.1 -X POST \
  "https://c21net-bas-api-doc-pipeline-ea-prod.scm.azurewebsites.net/api/zipdeploy?isAsync=true" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @/private/tmp/api-deploy.zip
# Expect HTTP 202 (accepted).

# 6. Deploy to Chat API (same zip — both services run from same codebase)
curl --http1.1 -X POST \
  "https://c21net-bas-api-prop-chat-ea-prod.scm.azurewebsites.net/api/zipdeploy?isAsync=true" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @/private/tmp/api-deploy.zip

# 7. Poll deploy status (~5 min for Oryx build)
TOKEN=$(az account get-access-token --resource "https://management.azure.com/" --query accessToken -o tsv)
for svc in c21net-bas-api-doc-pipeline-ea-prod c21net-bas-api-prop-chat-ea-prod; do
  echo "=== $svc ===" && \
  curl -s "https://${svc}.scm.azurewebsites.net/api/deployments" \
    -H "Authorization: Bearer $TOKEN" | python3 -c "
import json,sys
deps=json.load(sys.stdin)
for d in deps[:1]:
    print(d['id'][:16],'status:',d['status'],'complete:',d['complete'],d.get('status_text',''))
"
done

# 8. CRITICAL: Copy source files into wwwroot after Oryx build
# Oryx extracts zip to /tmp/zipdeploy/extracted/ and only puts the virtualenv in output.tar.zst.
# wwwroot keeps old source files unless explicitly overwritten. Must do this after every deploy.
TOKEN=$(az account get-access-token --resource "https://management.azure.com/" --query accessToken -o tsv)
for svc in c21net-bas-api-doc-pipeline-ea-prod c21net-bas-api-prop-chat-ea-prod; do
  echo "Copying source to $svc wwwroot..."
  curl -s -X POST "https://${svc}.scm.azurewebsites.net/api/command" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"command": "python3 -c \"import subprocess; r1=subprocess.run([chr(115)+chr(104),chr(45)+chr(99),chr(99)+chr(112)+chr(32)+chr(45)+chr(114)+chr(102)+chr(32)+chr(47)+chr(116)+chr(109)+chr(112)+chr(47)+chr(122)+chr(105)+chr(112)+chr(100)+chr(101)+chr(112)+chr(108)+chr(111)+chr(121)+chr(47)+chr(101)+chr(120)+chr(116)+chr(114)+chr(97)+chr(99)+chr(116)+chr(101)+chr(100)+chr(47)+chr(115)+chr(114)+chr(99)+chr(32)+chr(47)+chr(104)+chr(111)+chr(109)+chr(101)+chr(47)+chr(115)+chr(105)+chr(116)+chr(101)+chr(47)+chr(119)+chr(119)+chr(119)+chr(114)+chr(111)+chr(111)+chr(116)+chr(47)], capture_output=True, text=True); r2=subprocess.run([chr(115)+chr(104),chr(45)+chr(99),chr(99)+chr(112)+chr(32)+chr(45)+chr(114)+chr(102)+chr(32)+chr(47)+chr(116)+chr(109)+chr(112)+chr(47)+chr(122)+chr(105)+chr(112)+chr(100)+chr(101)+chr(112)+chr(108)+chr(111)+chr(121)+chr(47)+chr(101)+chr(120)+chr(116)+chr(114)+chr(97)+chr(99)+chr(116)+chr(101)+chr(100)+chr(47)+chr(97)+chr(112)+chr(105)+chr(32)+chr(47)+chr(104)+chr(111)+chr(109)+chr(101)+chr(47)+chr(115)+chr(105)+chr(116)+chr(101)+chr(47)+chr(119)+chr(119)+chr(119)+chr(114)+chr(111)+chr(111)+chr(116)+chr(47)], capture_output=True, text=True); print(r1.returncode, r2.returncode)\"", "dir": "/"}'
done

# 9. Restart both services so Python picks up the new source files
az webapp restart --name c21net-bas-api-doc-pipeline-ea-prod --resource-group c21net-bas-document-processor-ea-prod
az webapp restart --name c21net-bas-api-prop-chat-ea-prod --resource-group c21net-bas-document-processor-ea-prod

# 10. Verify health endpoints (wait ~30s after restart)
curl https://c21net-bas-api-doc-pipeline-ea-prod.azurewebsites.net/api/health
curl https://c21net-bas-api-prop-chat-ea-prod.azurewebsites.net/api/health
```

**Deploy notes:**
- Oryx build takes ~5 min; site starts ~2 min after build
- `requirements-api.txt` is the canonical dep list; it must be copied as `requirements.txt` at zip root — Oryx ignores all other names
- Do NOT use `az webapp deploy --type zip` or `az webapp deployment source config-zip` — both fail with connection drop on az CLI 2.84.0
- **MUST add `--http1.1` to curl zipdeploy** — HTTP/2 causes connection close (returns HTTP 000); `--http1.1` forces HTTP/1.1 and gets HTTP 202 correctly
- Both App Services share the same zip — the startup command determines which entrypoint runs
- Token expires after ~1 hour; refresh with `az account get-access-token` if deploy takes long
- **ZIP PITFALL:** Always run `rm -f /private/tmp/api-deploy.zip` as a SEPARATE command (not chained with `&&` after a command that might fail). `zip -r` in update mode silently reuses old content if the file already exists.
- **SOURCE FILES PITFALL:** Oryx extracts the zip to `/tmp/zipdeploy/extracted/` (temp), NOT to wwwroot. Oryx only puts the built virtualenv into `output.tar.zst` in wwwroot. Source files in wwwroot are NEVER updated by the deploy — only the virtualenv is. After every deploy, you MUST manually copy `/tmp/zipdeploy/extracted/src/` and `/tmp/zipdeploy/extracted/api/` to wwwroot via the Kudu command API (step 8 above), then restart both services (step 9).
- **`SCM_DO_BUILD_DURING_DEPLOYMENT=true` REQUIRED** — If set to false, Kudu extracts the zip but Oryx does NOT install packages. The app crashes with "No module named uvicorn". This must be `true` on both services or every deploy wipes the virtualenv.

### API Routes (verified live 2026-07-28 — grepped `@router.`/`@app.` decorators directly)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/auth/login` | None | Get JWT token |
| GET | `/api/health` | None | Health check |
| GET | `/api/config` | Bearer | Read runtime config |
| PUT | `/api/config` | Bearer | Update runtime config |
| POST | `/api/assistant/message` | `X-Api-Key` | WhatsApp/Slack assistant entry point (n8n calls this) |
| DELETE | `/api/assistant/session/{user_id}` | `X-Api-Key` | Clear a conversation session |

**Everything below is REMOVED — not registered in `doc_pipeline_main.py`, kept here only
so nobody goes looking for dead code:** `/api/chat/stream`, `/api/chat/report`,
`/api/search`, `/api/admin/triage`, `/api/admin/upload`, `/api/admin/runs`,
`/api/admin/history`, `/api/admin/documents`. The Next.js dashboard's Ingest/Process/
Vector DB/Chat/Search pages are therefore calling endpoints that no longer exist on this
service — if those pages are still expected to work, that's a separate gap to scope.

### Authentication & Security (`api/auth.py`)

**JWT:**
- Secret: `JWT_SECRET_KEY` env var. If missing, generates a random key per process — tokens invalidated on restart (acceptable for dev; never uses a known public string).
- Algorithm: HS256, TTL: 720 hours (30 days)

**Passwords (`DASHBOARD_USERS` env var):**
```
# Bcrypt hash (recommended)
DASHBOARD_USERS="admin:$2b$12$..."

# Multiple users
DASHBOARD_USERS="admin:$2b$12$...,user2:$2b$12$..."
```
To generate a hash: `python -c "import bcrypt; print(bcrypt.hashpw(b'PASSWORD', bcrypt.gensalt()).decode())"`

Single-user fallback: `DASHBOARD_ADMIN_PASSWORD` env var (plaintext, legacy).

The code warns when a plaintext password is detected and instructs to migrate to bcrypt.

**Rate limiting:** 5 login attempts per 60 seconds per IP (in-memory `defaultdict`). Returns HTTP 429 on breach.

**IMPORTANT — bcrypt import:** Use `import bcrypt` directly. Do NOT use `passlib` — it is incompatible with newer `bcrypt` versions and throws `MissingBackendError` / "password cannot be longer than 72 bytes".

### Report Endpoint (`POST /api/chat/report`)
```python
# Request body
{ "sources": [...], "district": "中環", "district_en": "Central", "report_type": "rent" }

# Response: application/pdf binary
# Critical: convert bytearray → bytes before returning
return Response(content=bytes(result.report.pdf_bytes), media_type="application/pdf", ...)
```

### CRITICAL: `src/nodes/__init__.py`
Must contain ONLY the docstring:
```python
"""Processing nodes for the document workflow."""
```
Any imports here cause `fitz` (PyMuPDF) to be loaded at startup → Azure App Service crash. The chatbot, report generator, and other nodes import `fitz` transitively; loading them at module init time breaks the API process.

---

## Azure Functions

**File:** `function_app.py`

| Trigger | Schedule | Purpose |
|---------|----------|---------|
| Queue | `pipeline-jobs` | `pipeline_job_worker` — durable pipeline job worker (WhatsApp/Slack/Teams/OneDrive dispatch) |
| Timer | `0 0 23 * * *` (23:00 UTC = 07:00 HKT) | `onedrive_sync` — Graph delta check on `MS_GRAPH_INBOX_FOLDER`, enqueues new files only (see UPDATE 2026-09-15 note above) |
| Timer | `0 55 15 * * *` (15:55 UTC = 23:55 HKT) | `daily_processing_summary` — Slack digest to `#doc-processor-alerts` |
| HTTP GET | `/api/health` | Health check (anonymous) |

**Corrected 2026-09-15:** the row previously here ("Timer, every 5 min, process 7 files per
batch from OneDrive /In") described the OLD v1 timer (`src/nodes/onedrive.py`, full folder
listing + move-to-`/Processed`) — that code was removed in the 2026-07-28 ingest-only pivot
and this table was never updated to match. `onedrive_sync` above is its intentionally
different replacement (delta-based, no move-to-processed), not a restoration of the old one.

**Production:** `c21net-bas-func-doc-pipeline-ea-prod.azurewebsites.net`
**Resource group:** `c21net-bas-document-processor-ea-prod` | **Subscription:** `c21net-business-automation-stack`

```bash
# Deploy (set subscription first — func CLI doesn't support --subscription)
az account set --subscription "c21net-business-automation-stack"
cd langgraph
func azure functionapp publish c21net-bas-func-doc-pipeline-ea-prod --python

# Disable timer
az functionapp config appsettings set --name c21net-bas-func-doc-pipeline-ea-prod \
  --resource-group c21net-bas-document-processor-ea-prod \
  --subscription "c21net-business-automation-stack" \
  --settings "AzureWebJobs.timer_trigger.Disabled=true"
```


## WhatsApp Assistant (added 2026-07-04)

**Principle: channels are media only.** WhatsApp, dashboard, and OneDrive all feed the same
pipeline codeline (`process_file_from_bytes` / `graph.py`). Never build channel-specific
processing paths.

### Flow
```
WhatsApp user → Twilio → n8n "WhatsApp Twilio Integration" (2KEkDoOvwKB7Y6Ml)
  → n8n sends ⏳ ack, downloads media (Twilio Basic Auth)
  → POST /api/assistant/message (X-Api-Key = ASSISTANT_API_KEY)
  → assistant fast paths or ReAct agent (src/nodes/assistant.py)
  → job enqueued to Storage Queue "pipeline-jobs"
  → Function App pipeline_job_worker runs the full pipeline
  → completion notification via n8n "WhatsApp Notify" webhook → Twilio → user
```

### Assistant fast paths (no LLM — instant reply, avoids OpenRouter 502/504 flakiness)
- Greeting/menu words → instant menu
- Image, no text → dup check → auto-dispatch (pipeline classifier decides news vs listing)
- PDF/other, no text → ask 知識文章 or 物業盤源
- File + listing trigger ("3"/"物業盤源"/"yes"...) in one message → dispatch immediately
- File + text ≥60 chars → forwarded post: the TEXT becomes the document content
  (`precomputed_ocr`, skips Azure DI), image kept for Odoo attachment
- "yes" after news duplicate warning → force-dispatch (checked BEFORE listing triggers)
- Anything else → ReAct agent (Qwen via OpenRouter) with tools: create_knowledge_article,
  process_property_listing, check_listing_duplicate, search_properties, query_odoo_listings

### Durable job queue
- `src/utils/job_queue.py`: `enqueue_pipeline_job()` (App Service) + `run_pipeline_job()`
  (Function App queue trigger). File bytes staged in blob container `pipeline-jobs`.
- Survives App Service restarts; 5 retries then poison queue; timer alerts ADMIN_WHATSAPP
  if poison queue is non-empty (`check_poison_queue`).
- Thread fallback if queue unavailable. Completion formatting lives in job_queue.py
  (NOT assistant.py — Function App must not import langchain).
- Pending-file cache is blob-backed: `src/utils/file_cache.py`, container
  `assistant-file-cache`, 30-min TTL — "3"/"yes" confirmations survive restarts.

### Known limitations
- **Twilio drops non-ASCII filenames** (Chinese → `?`). Backend sanitizes: strips `?`,
  falls back to `document-{timestamp}` if <3 chars remain. Chinese filenames only survive
  via dashboard uploads.
- **Twilio trial: 50 messages/day** — resets midnight UTC (8am HK). Upgrade removes cap.
- n8n passes `file_name_override` form field (UTF-8 text) because Node.js encodes binary
  Content-Disposition headers as Latin-1.
- **Forwarded posts sometimes arrive without caption text** (Twilio Body empty) — the image-OCR
  path handles them; DI reads the flyer content directly.
- **Job-blob cleanup gets 403** — AZURE_BLOB_WRITE_SAS lacks delete permission, so processed
  job files linger in `pipeline-jobs` container. Harmless; fix by regenerating SAS with `d` perm.

### DI cost guard (`src/utils/di_guard.py`)
- Counts OCR pages in Table Storage (table `DiUsage`), checked BEFORE every DI call
- Hard-stops past `DI_DAILY_PAGE_LIMIT` (default 200/day); WhatsApps `ADMIN_WHATSAPP` on trip
- Fails open if Table Storage unavailable; covers this codeline only (not the separate ETL project)

### Env vars added 2026-07-04
| Setting | Where | Purpose |
|---------|-------|---------|
| `ASSISTANT_API_KEY` | both + n8n | Auth for /api/assistant/message + notify webhook |
| `N8N_NOTIFY_WEBHOOK_URL` | both | n8n WhatsApp Notify webhook |
| `PIPELINE_QUEUE_CONN` | App Service | Storage conn string for pipeline-jobs queue (same account as Function App AzureWebJobsStorage) |
| `ADMIN_WHATSAPP` | both | Admin number for guard/poison alerts |
| `DI_DAILY_PAGE_LIMIT` | both (optional) | OCR daily page ceiling, default 200 |
| `AZURE_BLOB_READ_SAS`, `AZURE_TABLE_SAS`, `ODOO_API_KEY` | Function App | Were missing/stale — queue worker needs them |
| `TAVILY_API_KEY` (added 2026-08-04) | both | Used by `src/utils/url_fetcher.py` to enrich short OCR text containing URLs (e.g. `share.google` news forwards) before classify/extract. **Reused from `c21-property-chatbot`'s key, not dedicated** — shared free-tier quota, see memory `project-tavily-key-shared.md` |

### Env vars added 2026-09-15 (OneDrive sync)
| Setting | Where | Purpose |
|---------|-------|---------|
| `ONEDRIVE_SYNC_ENABLED` | Function App | Master off-switch for `onedrive_sync`. `false` unless baseline established — currently `true` |
| `ONEDRIVE_SYNC_MAX_AGE_DAYS` | Function App (optional) | Bounds a legitimate delta response, default 90 |
| `ONEDRIVE_MAX_FILE_MB` | Function App (optional) | Skip oversized files before enqueueing, default 25 |
| `ADMIN_SLACK_CHANNEL` | Function App | `#doc-processor-alerts` channel ID (`C0C1HJDUJR5`, C21net workspace) for the daily digest — reuses existing `SLACK_BOT_TOKEN` |

### Env vars added 2026-09-16 (folder repoint — supersede the pair below)
| Setting | Where | Purpose |
|---------|-------|---------|
| `ONEDRIVE_SYNC_DRIVE_ID` | Function App | Stephen Wong's OneDrive (`stephenwong@c21net.com`), drive `b!WQGaAOw2aUefyqasQw331EB7h2cpTQFDmJwEqF5UC-L2jKz1LwTGS7SgLqPDhGLx` — same drive `bas-stacks`' onedrive-sync watches |
| `ONEDRIVE_SYNC_FOLDER_PATH` | Function App | `Building_Folder/BD_Commercial` — the real, actively-used folder; replaces the dormant `admin@c21net.com` / `Document Processor/In` originally used on 2026-09-15 |

~~`MS_GRAPH_DRIVE_ID`, `MS_GRAPH_INBOX_FOLDER`~~ — no longer used by `onedrive_sync` as of the
2026-09-16 repoint (still used by the unrelated legacy `scripts/process_inbox.py`,
`scripts/check_onedrive.py`, and the admin config route — deliberately left alone, not
part of this feature's scope).

## Ingest & Triage

### Supported Upload Formats
`SUPPORTED_FORMATS = {"pdf", "jpg", "jpeg", "png", "docx", "pptx"}` (defined in `api/routes/admin.py`)

Unsupported formats (e.g. `.xls`, `.doc`, `.ppt`, `.mp4`) are rejected at triage and logged to Azure Table Storage with `status="unsupported"`.

### Triage Endpoint (`POST /api/admin/triage`)
Single-file endpoint called before uploading. Steps:
1. Check extension against `SUPPORTED_FORMATS` — if not supported, log and return `can_process: false`
2. Run Azure DI `prebuilt-read` on first 2 pages (PDFs) or full file (images/docs)
3. Quick LLM classify (`call_openrouter` from `src/nodes/classifier.py`) on first 3000 chars
4. Return `{ file_name, can_process, detected_type, format, confidence, reason }`

Designed to be fast (~3–5s) — only first 2 pages, no full pipeline.

### Azure Table Storage — Processing History
**Account:** `blobhk04472` | **Table:** `ProcessingHistory`
**SAS env var:** `AZURE_TABLE_SAS`

**Functions in `src/utils/table_storage.py`:**
- `log_run(...)` — called by `process_file()` in `graph.py` after every pipeline run
- `log_unsupported(file_name, ext)` — called by triage for unsupported formats
- `list_runs(months, top)` — used by `GET /api/admin/history`

**PartitionKey** = `YYYY-MM` (monthly partitions for fast range queries)
**Status values:** `"success"`, `"error"`, `"unsupported"`

If `AZURE_TABLE_SAS` is not set, all logging silently skips — never crashes the pipeline.

---

## Known Issues

### 409 Conflict on Move to /Processed
**Fix:** `@microsoft.graph.conflictBehavior: replace` in `move_to_processed()` (`src/nodes/onedrive.py`).

### Multi-Index Search Not Working
**Cause:** `AZURE_SEARCH_INDEXES` missing from Azure App Service settings.

### Report Shows 0 Properties
**Cause:** `listing_list` has two formats — `extracted_data.units[]` (old) and `extracted_data.items[].units[]` (new). Statistics module handles both.

### PDF Report Chinese Font
**Problem:** Chinese building names may show as boxes in PDF reports.
**Debug:** Add logging to `_get_chinese_font()` in `pdf_generator.py`.

### Azure App Service Startup Crash (`fitz` / PyMuPDF)
**Problem:** API process crashes at startup with `ImportError` related to `fitz`.
**Cause:** `src/nodes/__init__.py` had imports (`from src.nodes.ocr import ...`) which pulled in PyMuPDF transitively. Azure App Service cannot load the binary extension at import time.
**Fix:** `src/nodes/__init__.py` must contain ONLY `"""Processing nodes for the document workflow."""` — no imports.

### passlib Incompatible with bcrypt ≥ 4.0
**Problem:** `passlib` throws `MissingBackendError` or `ValueError: password cannot be longer than 72 bytes`.
**Fix:** Use `import bcrypt` directly in `api/auth.py`. `passlib` is kept in `requirements.txt` for backward compat but not imported in auth code.

### Report PDF: `bytearray` vs `bytes` in FastAPI
**Problem:** `starlette.responses.Response` calls `.encode()` on content; `bytearray` lacks this method → "Load failed" in browser.
**Fix:** `content=bytes(result.report.pdf_bytes)` in `api/routes/chat.py`.

---

## Known Issues & Fixes Backlog

### 🔴 1. `processed-documents` Index is Empty
**Problem:** 0 docs in `processed-documents` on new search service (`c21net-bas-aisearch-ea-prod`). Chatbot and Search tab only find docs from `c21net-intelligence-v2` (771 docs). ~124 old docs were never reprocessed after migration.

**Fix:** Drop the old 124 docs back into OneDrive `/Document Processor/In` — timer will pick them up and reindex into `processed-documents`.

---

### 🟡 2. Double OCR on Manual Upload
**Problem:** When using the Ingest tab, Azure Document Intelligence is called twice for the same file:
- `POST /api/pipeline/triage` → DI on first 2 pages
- `POST /api/pipeline/process` → DI on ALL pages again

Two DI transactions per manual upload — unnecessary cost.

**Fix:** In `api/routes/pipeline.py`, pass the triage OCR result (text + page_count) as part of the process request body, and skip the DI call in `process_file()` if OCR text is already provided. Store triage result in browser state between triage and process steps.

**Files to change:**
- `api/routes/pipeline.py` → `process_file()` — accept optional pre-computed OCR text
- `app/(app)/admin/ingest/page.tsx` → pass triage OCR result when calling `processIngest()`
- `lib/api.ts` → update `processIngest()` signature

---

### 🟡 3. `MOVE_WHEN_DONE=false` on Timer
**Problem:** After the timer processes a file from OneDrive `/In`, it stays there. Nothing moves it to `/Processed`. Risk of reprocessing on next timer run.

**Verify first:** Check that `function_app.py` skips files already indexed in Azure AI Search before reprocessing. If skip logic exists and works → low risk, leave as-is. If not → reprocessing will happen every 5 min.

**Fix (option A):** Set `MOVE_WHEN_DONE=true` in Function App env vars:
```bash
az functionapp config appsettings set \
  --name c21net-bas-func-doc-pipeline-ea-prod \
  --resource-group c21net-bas-document-processor-ea-prod \
  --subscription "c21net-business-automation-stack" \
  --settings "MOVE_WHEN_DONE=true"
```
**Fix (option B):** Confirm skip-if-indexed logic in `function_app.py` and keep as-is.

---

### 🟡 4. `blobhk04472` Still on Old Subscription
**Problem:** All blob storage (PDFs, images) and Table Storage (ProcessingHistory) live on old subscription (`Azure subscription 1` / `blob-storage-hk-rg`). Split billing — if old subscription lapses, everything breaks.

**Fix:** Full storage migration:
1. Create new storage account in `c21net-bas-document-processor-ea-prod`
2. Copy `property-pdf` blob container contents (azcopy)
3. Copy `ProcessingHistory` table (azcopy or script)
4. Copy `document-images` blob container
5. Generate new SAS tokens
6. Update env vars on both Function App and API:
   - `AZURE_BLOB_ACCOUNT`
   - `AZURE_BLOB_WRITE_SAS`
   - `AZURE_TABLE_SAS`
   - `AZURE_BLOB_CONTAINER`
   - `AZURE_BLOB_IMAGES_CONTAINER`

---

### 🟢 5. Function App and API Share B1 Plan
**Problem:** `c21net-bas-asp-ea-prod` (B1, 1 core, 1.75GB RAM) runs both the Function App and the API. Heavy batch processing (7 PDFs) while users are on chatbot → both slow down.

**Fix:** Upgrade plan to B2, or move Function App to a Consumption plan (pay-per-execution, scales independently):
```bash
# Option A: upgrade shared plan to B2
az appservice plan update \
  --name c21net-bas-asp-ea-prod \
  --resource-group c21net-bas-document-processor-ea-prod \
  --subscription "c21net-business-automation-stack" \
  --sku B2
```
**Note:** Only needed if performance becomes an issue. Fine for current traffic.

---

### 🟢 6. No Error Boundaries in Next.js
**Problem:** If an API call throws an unhandled error, the whole page crashes with a blank screen. No fallback UI shown to the user.

**Fix:** Add `error.tsx` files next to each `page.tsx` in the App Router — Next.js automatically uses these as error boundaries:
- `app/(app)/chat/error.tsx`
- `app/(app)/admin/ingest/error.tsx`
- `app/(app)/admin/process/error.tsx`
- `app/(app)/admin/vector/error.tsx`

```tsx
// error.tsx pattern
"use client";
export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="p-6 text-red-500">
      <p>Something went wrong: {error.message}</p>
      <button onClick={reset}>Try again</button>
    </div>
  );
}
```

---

## Planned: Manual Data Editor

**Status:** Not implemented | **Location:** Admin → Vector Database tab → Edit button per document

### Purpose
Allow admins to correct AI-extracted data directly from the dashboard.

### Storage
Edits saved to Azure AI Search `extracted_data` field via merge (preserves unedited fields). Smart merge ensures manual edits survive reprocessing if AI returns null.

### UI Design (Admin → Vector tab)
- "Edit" button per document row → expands form in-place
- **Standard fields** (text/number/dropdown): building_name, address, district, property_type, size_sqft, rent_monthly, floor_unit, contact_name, contact_phone, contact_email
- **Custom fields** section: add/remove arbitrary key-value pairs
- "Save" → PATCH to Azure AI Search, refresh cache

### API for Saving
```python
def update_document_extracted_data(doc_id: str, extracted_data: dict):
    url = f"{SEARCH_ENDPOINT}/indexes/{INDEX}/docs/index?api-version=2024-07-01"
    body = {
        "value": [{
            "@search.action": "merge",
            "id": doc_id,
            "extracted_data": json.dumps(extracted_data, ensure_ascii=False)
        }]
    }
    # POST with api-key header
```

---

## Code Review (2026-06-13)

Principal-grade review was conducted and documented externally:
- **Confluence:** https://c21net.atlassian.net/wiki/x/BAD_AQ ("Document Processor — Code Review, Principal Grade, 2026-06-13")
- **Notion:** https://app.notion.com/p/37eecf49be518179839cd376c418dbf6

Key findings acted on:
1. **JWT secret fallback** — was hardcoded string `"change-me-in-production"`, changed to `secrets.token_hex(32)` per-process random key
2. **Plaintext passwords** — `verify_credentials()` now bcrypt-checks `$2b$`/`$2a$` hashes; plaintext falls back with warning to migrate
3. **No rate limiting on login** — added in-memory per-IP rate limit (5 attempts / 60 sec) via `_check_rate_limit()`

---

## Monthly Costs

| Service | Cost |
|---------|------|
| Azure Static Web Apps (Next.js) | Free tier |
| Azure App Service (FastAPI) | ~$15-20/mo (B1) |
| Azure AI Search | ~$70/mo |
| Azure OpenAI | ~$5-20/mo |
| Azure Functions | ~$0-5/mo |
| OpenRouter (LLM) | ~$1-5/mo |
| Tavily (Web Search) | Free (1k/mo) |
| LangSmith | Free tier |
| **Total** | **~$95-120/mo** |

---

## Extraction Memory (AI Self-Improvement)

**Status:** Phase 1 LIVE (2026-07-05) · Phases 2–3 planned

The system learns from past successful extractions rather than processing every document cold.

### Phase 1 — Few-shot Extraction Memory ✅ IMPLEMENTED
**File:** `src/nodes/extractor.py` — `fetch_examples(text_sample, doc_type)`

Before extraction, keyword-searches `processed-documents` for the top 2 past extractions of the
same document_type and prepends them to the prompt as reference examples (with an instruction
not to copy values). Fails open on any error. Skips docs with `_extraction_failed`.

### Phase 2 — Correction Learning (Human-in-the-loop)
**Depends on:** Manual Data Editor being built first

When an admin corrects extracted data via the Manual Editor, mark that document as a gold standard example — weight it higher in Phase 1 retrieval.

**Changes:**
- `src/nodes/indexer.py` — add `is_example` (bool) and `example_weight` (int) fields to index schema
- `api/routes/admin.py` — `PATCH /documents/{id}` already exists; add `is_example` flag support
- `app/(app)/admin/ingest/page.tsx` — "Mark as example" button after successful processing

### Phase 3 — Self-Improving Prompts
**File:** New background task or admin endpoint

Periodically analyse failed/weak extractions (many null fields, low confidence) and suggest prompt improvements for human review.

**Changes:**
- New script or `GET /api/admin/prompt-suggestions` endpoint
- Queries Azure Table Storage for runs with high null-field rate
- Sends patterns to gpt-5-mini → returns suggested prompt edits
- Admin reviews and applies to `PROMPTS` dict in `src/nodes/extractor.py`

### Data Already Available (No Migration Needed)
- Past extracted data → `processed-documents` index, `extracted_data` field
- Vector embeddings → `content_vector` field (1536 dims, already indexed)
- Run history → Azure Table Storage `ProcessingHistory`
- Manual corrections → Manual Data Editor (once built)
