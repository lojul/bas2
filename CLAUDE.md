# bas2 — one repository for C21 document processing and BAS 2.0

This repository holds every project we own in the document-processing / property-AI
area, so there is one place to look. It was created on 2026-10-08 by importing the
existing repositories with their full git history (no code changes).

Plan for BAS 2.0 (one-page summary, architecture, document add-on, implementation plan):
https://claude.ai/code/artifact/90d4a48f-0eab-4a0e-b01e-0fbfed1edef5

## BAS 2.0 — decisions and build order (2026-10-15)

Full reasoning, connector catalog and pricing: tab "SaaS, connectors and Odoo" in the plan doc above.

**What BAS 2.0 is:** the AI layer over a company's own data. It reads the customer's systems
(SQL database, documents, or a business system such as Odoo) into one searchable store, and
staff talk to it on web, Slack, WhatsApp and Teams; outside AI agents use the same tools
through the BAS MCP server. The customer's system stays the system of record.

**Decisions**
- Product working name: **Genie** (genie.infiniduo.com). Final name chosen before public launch;
  keep the name in one config value so a rename is cheap. Shortlists are parked in the plan doc.
- Sold by **Infinity Duo Technology** (Stripe account exists, test mode).
- Multi-tenant SaaS on subscription plans (Starter / Business / Enterprise + Document add-on;
  document -> Odoo/SQL field mapping is quoted customisation only).
- Platform: **Supabase** — Postgres + pgvector, Supabase Auth, Supabase Vault, Storage.
  One shared schema; every row carries `tenant_id`; row-level security enforces isolation.
  Region: ap-southeast-1 (Singapore), closest to HK.
- **Odoo is optional.** No connector is mandatory. Phase 1 connectors: SQL database (read-only),
  CSV/spreadsheet upload, Odoo 19/20 via the JSON-2 API, Odoo 20 MCP. XML-RPC (Odoo 18 and older)
  only if a paying customer needs it — deprecated since Odoo 19.
- **BAS 2.0 does not depend on C21.** Development and demos run on our own new Odoo 20
  environment plus a SQL-only demo tenant. C21 stays on `legacy/` and can join later as an
  ordinary tenant by connecting its own Odoo — no data migration into our Odoo 20.
- AI: bring-your-own-key (Anthropic, xAI/Grok, OpenRouter, Azure OpenAI) through one model
  gateway, plus our own metered key as the default.
- Billing: Stripe Billing + customer portal; meter messages, OCR pages, tokens and synced
  records per tenant from day one.

**Demo data (proposed, to confirm)**
- Demo tenant A (property, on our Odoo 20): Odoo's built-in demo data for CRM/contacts, plus a
  listing model shaped like C21's `x_c21_listing`, filled with ~200 synthetic listings (real public
  building names and districts; invented units, prices, owners and phone numbers).
- Demo tenant B (generic SME, SQL only): a small Postgres sample database — proves Odoo is optional.
- Do **not** copy C21's live contacts, owners or listings into a demo (client personal data, PDPO).
  Reuse C21 flyers/floor plans for the document demo only with C21's written OK.

**Build order**
1. `shared/` — Supabase project, tenants, users + roles, RLS, Vault, pgvector storage schema.
2. `portal/` — Genie sign-up, invites, Microsoft/Google sign-in; replace the browser-stored token.
3. `sync/` — SQL + CSV connectors, then Odoo 20 (JSON-2); one mapping screen.
4. `outbound/` — BAS MCP server + agent: source-neutral versions of the property-chatbot tools
   (search records, search knowledge, find contact, create lead/record, web search),
   model gateway, per-tenant guardrails.
5. Web chat + Slack app; Stripe plans and usage metering on.
6. Gate: both demo tenants pass a fixed question set; then the first paying customer.
7. Phase 2: WhatsApp (Meta Cloud API, Embedded Signup), Teams, email intake, Odoo MCP mode.
   Phase 3: document add-on moved from `legacy/document-processor`.

**Needed before each step**
- Step 1: create the Supabase project (free tier for development; Pro before the first paying
  tenant — free projects pause when idle).
- Step 3: Odoo 20 environment URL + API key for a dedicated integration user.
- Step 4: a platform OpenRouter key (optionally Anthropic / xAI keys to test bring-your-own-key).
- Step 5: a Slack app for the Genie install; Stripe test-mode keys (Infinity Duo Technology).

## Which folder to use

| Folder | What it is | Deploys to | Status | Retires at |
|---|---|---|---|---|
| `legacy/document-processor/` | Document ingest: WhatsApp / Slack / Teams / OneDrive → OCR → classify → extract → Odoo. Python, LangGraph. Has its own detailed `CLAUDE.md`. | App Service `c21net-bas-api-doc-pipeline-ea-prod` + Function App `c21net-bas-func-doc-pipeline-ea-prod` (`./deploy.sh`) | Live | End of BAS 2.0 phase 3 |
| `legacy/genie-dashboard/` | Web dashboard at genie.infiniduo.com (Next.js, Vercel) | Vercel (currently built from the old GitHub repo, see Switch-over) | Live | Becomes `portal/` in phase 4 |
| `legacy/n8n/` | n8n workflow exports (WhatsApp/Slack glue). **Keys redacted** — see Secrets | n8n | Live | End of phase 3 |
| `legacy/odoo-bas-sync/` | Daily Odoo `x_c21_listing` → BAS `properties-index` sync (Azure Function) | Azure Function App | Live | End of phase 1 |
| `legacy/property-chatbot/` | Staff Slack bot: property search over `properties-index`, CRM leads, contacts | App Service + Function App (RG `c21net-bas-property-chatbot-ea-prod`) | Live | End of phase 1 |
| `legacy/document-processor-notes/` | Loose planning notes and the Obsidian vault that sat beside the document processor | — | Reference | — |
| `sync/`, `documents/`, `outbound/`, `portal/`, `shared/` | BAS 2.0 projects (bas2-sync, bas2-documents, bas2-outbound, bas2-portal, shared storage schema). See "BAS 2.0 — decisions and build order" above. | Supabase (project not yet created) + Vercel | Not started — step 1 (`shared/`) next | — |

**Not in this repo, on purpose:**
- `c21-leasing` (www.c21net.com) — the public website; different audience and lifecycle.
- `bas-stacks` — another developer's project; reference only, never copy code without their agreement.
- `knowledge-sync-client` — lives in the `c21net` GitHub org; ownership not yet confirmed.

## Rules

- `legacy/` gets fixes only, no new features. New work goes into the BAS 2.0 folders.
- Delete a `legacy/` folder only when its BAS 2.0 replacement has passed its gate.
- Never commit `.env`, `local.settings.json` or keys (see `.gitignore`). Legacy secrets live in Azure app settings / Key Vault; BAS 2.0 customer keys live in Supabase Vault, never in tables or code.
- One copy only: once a project is switched over (below), stop editing its old local folder.

## Switch-over status

The old repositories still exist and are still what deployments use. Until a row is
ticked, the old location is the source of truth and this copy is a snapshot.

| Project | Old GitHub repo | Old local folder | Switched to bas2? |
|---|---|---|---|
| document-processor | lojul/c21-document-processor | `~/Active Projects/document processor/langgraph` | No |
| genie-dashboard | lojul/property-intelligence-dashboard | `~/Active Projects/document processor/nextjs-dashboard` | No (needs Vercel root directory → `legacy/genie-dashboard`) |
| odoo-bas-sync | lojul/odoo-bas-sync | `~/Active Projects/odoo-bas-sync` | No |
| property-chatbot | lojul/c21-property-chatbot | `~/Active Projects/c21-property-chatbot` | No |

### Changes made in the old repos after the import

The old repos are still where changes are made and deployed from. The `legacy/` copy
is refreshed afterwards with `git subtree pull` (history kept), e.g.
`git subtree pull --prefix=legacy/document-processor "<old local folder>" master`.

| Date | Project | Change | `legacy/` copy up to date? |
|---|---|---|---|
| 2026-10-15 | document-processor | New upload channel: Odoo **C21 放盤管理 → 文件上傳**. A staff upload in Odoo triggers a webhook to `POST /api/odoo/upload`, the file goes through the same pipeline as WhatsApp/Slack, and the result is written back to the Odoo record. The Odoo side is built with Studio-compatible records (model `x_c21_doc_upload`) by `scripts/setup_odoo_doc_upload.py`. Live since 2026-10-15. Details: `legacy/document-processor/CLAUDE.md` (UPDATE 2026-10-15). | Yes, synced to old repo commit `c956e1a` |

To switch one: recreate its virtualenv / `node_modules` inside this repo, deploy once
from here and verify behaviour, then archive the old GitHub repo with a README pointing here.

## Secrets

The n8n exports in `legacy/n8n/` contained live keys (OpenRouter, Azure OpenAI,
Document Intelligence, Azure Search, Odoo, PDF.co, and a blob SAS token valid until
2028-03-31). They are replaced with `REDACTED` here. The unredacted originals are
still in `~/Active Projects/document processor/n8n/` (never pushed). Rotating those
keys is recommended.
