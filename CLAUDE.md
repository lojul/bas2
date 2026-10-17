# bas2 — one repository for C21 document processing and BAS 2.0

This repository holds every project we own in the document-processing / property-AI
area, so there is one place to look. It was created on 2026-10-08 by importing the
existing repositories with their full git history (no code changes).

**Concept and technical overview of what is built (Genie): `docs/genie-overview.md`** — start there.

Plan for BAS 2.0 (one-page summary, architecture, document add-on, implementation plan):
https://claude.ai/code/artifact/90d4a48f-0eab-4a0e-b01e-0fbfed1edef5

## BAS 2.0 — decisions and build order (2026-10-15)

Full reasoning, connector catalog and pricing: tab "SaaS, connectors and Odoo" in the plan doc above.

**What BAS 2.0 is:** the AI layer over a company's own data. It reads the customer's systems
(SQL database, documents, or a business system such as Odoo) **live, at the moment a question is
asked**, and staff talk to it on web, Slack, WhatsApp and Teams; outside AI agents use the same tools
through the BAS MCP server. The customer's system stays the system of record.

**No copy of customer data (user decision 2026-10-16):** "we don't store stuff in Genie, we should
not." Genie stores only accounts, workspaces, members, connection details, encrypted keys (Vault) and
usage counts — never the customer's records. The earlier "copy into one searchable store" design
(sync, `records` table) is retired for customer data; `records` only holds the synthetic demo tenant
until it gets its own demo SQL database. Consequences: no sync jobs, no embedding index of customer
data; CSV upload and the document add-on need a design that reads files where they live.
**Exception — saved chats (user decision 2026-10-17):** Ask keeps chats (`chats`, `chat_messages`) so members can
share them: Team chats (all members, Genie answers on @Genie) and Private chats (author only, Genie answers every
message). Deleted automatically 90 days after the last message (pg_cron `genie-chat-retention`), or earlier by the
author / an owner or admin. Live updates via Supabase Realtime. Privacy policy updated.

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
- Billing: Stripe Billing + customer portal; meter messages, OCR pages, tokens and tool
  records per tenant from day one.

**Demo data (proposed, to confirm)** — tenant B *Harbour Supplies (Demo)* was seeded on 2026-10-15 and
**deleted from `genie` on 2026-10-16 at the user's request**; the seed file stays at
`shared/supabase/seed/demo_tenant_b.sql` (synthetic records, no Odoo) for when a demo is needed again.
- Demo tenant A (property, on our Odoo 20): Odoo's built-in demo data for CRM/contacts, plus a
  listing model shaped like C21's `x_c21_listing`, filled with ~200 synthetic listings (real public
  building names and districts; invented units, prices, owners and phone numbers).
- Demo tenant B (generic SME, SQL only): a small Postgres sample database — proves Odoo is optional.
- Do **not** copy C21's live contacts, owners or listings into a demo (client personal data, PDPO).
  Reuse C21 flyers/floor plans for the document demo only with C21's written OK.

**Build order**
1. `shared/` — Supabase project, tenants, users + roles, RLS, Vault, pgvector storage schema.
   **Done 2026-10-15** (branch `bas2/shared-schema`): project `genie`, ref `xhaqzwznduxoosqtcrrm`,
   ap-southeast-1, free tier. See `shared/README.md`.
2. `portal/` — Genie sign-up, invites, Microsoft/Google sign-in; replace the browser-stored token.
   **In progress**, live at genie.infiniduo.com: sign-in with email + password, forgot-password; invitees set
   their password on the invite link. Google and Microsoft are set up (Entra client secret expires 2028-10-15) but
   shown as **"Coming soon"** until ready (`SOCIAL_SIGNIN_READY` in `portal/lib/auth-settings.ts`, user 2026-10-17); workspaces, members and
   invite links; sidebar layout with Help centre; one Settings page (data sources, AI model keys, AI agent
   access). Email sign-in links were dropped (they failed on the live site). See `portal/README.md`.
   Still open: email sending (custom SMTP, e.g. Resend) — until then Supabase only emails members of the
   Supabase organisation, so invites/resets/sign-up confirmations don't reach customers; Google sign-in
   is in Testing mode (only listed test users) until published.
3. Data sources — Odoo first, then SQL; read live, nothing stored.
   **Odoo live (2026-10-16)**: portal → workspace → Settings → Data sources → switch Odoo on (C21:
   workspace `c21`, address `https://c21net.odoo.com`, database taken from the address). Ask and the MCP
   server read Odoo at question time (`portal/lib/odoo`). The copy/sync design of 2026-10-15 is removed.
   **C21's document index live (2026-10-16)**: Settings → Data sources → Document search index — C21's own
   Azure AI Search `properties-index` (SharePoint building folders, proposals, listings) on
   `c21net-bas-srch-ea-prod`, read-only query key `genie-readonly`. Feeds `search_knowledge`. The legacy
   jobs that build this index must keep running while Genie uses it (was "retire at end of phase 1").
   Vector search needs a vectorizer on the index (Azure OpenAI `text-embedding-3-large`) — user to decide;
   adding it needed an OpenAI key copied into the search service, which Claude was not allowed to do.
   Still to come: SQL database (live, read-only).
4. `outbound/` — BAS MCP server + agent: source-neutral versions of the property-chatbot tools
   (search records, search knowledge, find contact, create lead/record, web search),
   model gateway, per-tenant guardrails.
   **MCP server in progress** (branch `bas2/outbound-mcp`): it lives in the portal at
   `https://genie.infiniduo.com/api/mcp` (`portal/app/api/mcp`, `portal/lib/mcp`), authenticated by
   workspace API keys (portal → workspace → Settings → AI agent access). Read tools: workspace_info, search_records,
   get_record, find_contact, search_knowledge, each backed by an `mcp_*` database function. Still to
   come: create lead/record (needs write-back connectors), web search, semantic search (needs the
   embedding job).
   **Agent + model gateway in progress** (same branch), also in the portal: "Ask" tab at
   `/app/<workspace>/ask`; `portal/lib/ai` — gateway picks the workspace's own key (Anthropic, then
   OpenRouter, then xAI, read from Vault) or the platform key; Claude runs through the Anthropic SDK
   (`claude-opus-5-5`, server-side fallbacks on), OpenRouter/xAI through their OpenAI-compatible APIs.
   Tools run as the signed-in member via `agent_tool()`; messages and tokens are metered in
   `usage_events`. Azure OpenAI keys are saved but not used by chat yet (needs endpoint + deployment).
   `outbound/` stays reserved in case the agent moves out of the portal (e.g. for Slack/WhatsApp workers).
5. Web chat + Slack app; Stripe plans and usage metering on.
   **Slack built 2026-10-16** (Settings → Channels; `portal/README.md` → Slack). C21's existing bot is
   `c21_property_chatbot` in Slack workspace C21net, today served by Azure Function
   `c21net-bas-func-chatbot-slack-ea-prod` (`/api/slack/events`); moving it to Genie = paste its keys in Genie and
   change the app's Request URL. **WhatsApp built 2026-10-17** on Twilio's shared Sandbox (+1 415 523 8886, trial
   account): text → Genie, photos/files → forwarded unchanged to C21's n8n document intake, so that keeps working.
   A real C21 WhatsApp number (Meta-approved) is needed before staff use it.
6. Gate: both demo tenants pass a fixed question set; then the first paying customer.
7. Phase 2: WhatsApp (Meta Cloud API, Embedded Signup), Teams, email intake, Odoo MCP mode.
   Phase 3: document add-on moved from `legacy/document-processor`.

**Needed before each step**
- Step 1: ~~create the Supabase project~~ done (free tier for development; upgrade to Pro before
  the first paying tenant — free projects pause when idle).
- Step 3: Odoo 20 environment URL + API key for a dedicated integration user.
- Step 4: ~~Vercel env vars `SUPABASE_SECRET_KEY` and `OPENROUTER_API_KEY`~~ added 2026-10-15. The platform AI key
  is **OpenRouter only** — no platform `ANTHROPIC_API_KEY` (decided 2026-10-15); workspaces can still add
  their own Anthropic key. **The OpenRouter account is registered in Hong Kong, so Anthropic, OpenAI and Google
  models are refused (403 "violation of provider Terms Of Service", 2026-10-16).** The gateway sends a fallback
  list: `GENIE_OPENROUTER_MODEL` (comma-separated, optional) then `qwen/qwen3.8-max-0902`,
  `deepseek/deepseek-v4-pro-0813`, `z-ai/glm-5.3` (max 3), with `provider.data_collection = deny`. Claude for
  C21 needs a workspace's own Anthropic key or a non-HK platform account.
- Step 5: a Slack app for the Genie install; Stripe test-mode keys (Infinity Duo Technology).

**Done 2026-10-16/17 (PRs #19–#41):** live Odoo + C21's document index as data sources (on/off cards, Save,
Test connection, keys masked with show/copy); per-workspace model choice (platform OpenRouter account is in
Hong Kong → Qwen default, no Claude/GPT/Gemini on it); Copilot-style Ask as the home page (Overview removed);
ERPNext look, 16px base; Slack channel (Settings → Channels) connected to C21's `c21_property_chatbot` — first
real Slack question still to be confirmed; usage metering fixed; faster navigation (one auth check per
request, loading screen, Settings builds one tab). Demo tenant B deleted.

**Pending and next (updated 2026-10-17, end of day)** — overview of what's built: `docs/genie-overview.md`.

**Changes in Odoo from Ask (PR #59, 2026-10-17; test on C21 live):** off by
default; Settings → Data sources → Changes in Odoo; every change is a draft confirmed by the requester or an
owner/admin; log in Settings → Activity; web only. Details `portal/README.md`. Second exception to "no copy": a
draft's values for ≤24 h, then only who/what/which record for a year.
Writes use their own Vault key (`odoo_write_key`, card field "API key of the Genie Odoo user"), kept separate from
the reading key on purpose (user decision 2026-10-17). C21 has only one Odoo user, so the user pasted **the same
key** into both; a dedicated user's key can replace it later without touching reading. C21 status: switched on,
create lead / contact / note / follow-up on for members, update fields off, limit 50 — no change tested yet.
**UI tweaks 2026-10-17 (PRs #53–#61):** saved team/private chats listed under Ask in the sidebar; Team page keeps
invitation history with "New link"; Twilio-console-like larger text and spacing (text-sm 16px); no hint text next
to Private (Team: "Write @Genie to ask Genie"); sidebar Data sources / Channels are plain status lines (no link,
no hover).

*Waiting on the user (built, not yet confirmed working end to end):*
| Item | What's needed |
|---|---|
| Slack | Request URL `https://genie.infiniduo.com/api/slack/c21/events` set in the Slack app ("Verified"), then one @mention test |
| WhatsApp | Twilio Sandbox "When a message comes in" → `https://genie.infiniduo.com/api/whatsapp/c21/inbound` (POST), then a text + a photo test |
| Changes in Odoo | Set up and switched on for C21 (same key pasted). Test on Ask in a Private chat with "TEST …" records (create lead → Confirm → note → follow-up), check Settings → Activity, then delete the TEST records in Odoo |
| Team chat | Two members in one Team chat: live updates + @Genie answer |
| Usage metering | One answer on Ask, then check `usage_events` has `message` / token rows (fix shipped, unverified) |
| C21 trial | 3–5 agents use Ask/Slack/WhatsApp for a week; collect wrong / missing / slow answers |

*Decisions the user still has to make:*
- Answer layout: short answer, then "From Odoo (live)" / "From documents", Odoo wins on current facts (proposed).
- Vector search on C21's index: add an Azure OpenAI vectorizer to `properties-index` (needs the user to run it or
  approve a managed identity — Claude may not copy the OpenAI key).
- AI agent access (MCP) as an on/off card like the others (proposed).
- When to switch on Google / Microsoft sign-in (`SOCIAL_SIGNIN_READY`) and publish the Google consent screen.

*Suggested build order:*
1. Fix what the C21 trial shows (search quality on listings, speed, answer layout).
2. ~~Actions in Odoo from chat~~ built 2026-10-17 (web only); next: the same on Slack/WhatsApp once members are linked to their Slack user / phone.
3. Email sending via Resend (Resend account + infiniduo.com DNS): emailed invites with a 6-digit code (closes the
   "held invite link = key" gap), password reset and sign-up confirmation for everyone.
4. Stripe plans, limits and a usage page (Stripe test keys from Infinity Duo Technology).
5. Document add-on: flyer/photo → Odoo, rebuilt into Genie (today WhatsApp files go to the legacy n8n pipeline).
6. More live sources (read-only SQL; SharePoint/OneDrive or Google Drive search), Teams, a real WhatsApp number.

*Housekeeping:* rotate the n8n keys (see Secrets); Supabase Pro before the first paying tenant; archive the old
`lojul/property-intelligence-dashboard` repo; keep legacy `odoo-bas-sync` and the old Slack Azure Function running
(the first fills `properties-index`, the second is the fallback if Slack is pointed back); renew the Microsoft Entra
client secret before 2028-10-15.
Dropped by the no-copy decision: scheduled sync, embedding index over customer data, CSV upload into Genie.

## Which folder to use

| Folder | What it is | Deploys to | Status | Retires at |
|---|---|---|---|---|
| `legacy/document-processor/` | Document ingest: WhatsApp / Slack / Teams / OneDrive → OCR → classify → extract → Odoo. Python, LangGraph. Has its own detailed `CLAUDE.md`. | App Service `c21net-bas-api-doc-pipeline-ea-prod` + Function App `c21net-bas-func-doc-pipeline-ea-prod` (`./deploy.sh`) | Live | End of BAS 2.0 phase 3 |
| `legacy/genie-dashboard/` | Old web dashboard (Next.js static export). **Replaced by `portal/` at genie.infiniduo.com (decided 2026-10-15)**; C21 gets a workspace in the portal instead | — (Vercel project now builds `portal/`) | Retired | Delete once the portal is live |
| `legacy/n8n/` | n8n workflow exports (WhatsApp/Slack glue). **Keys redacted** — see Secrets | n8n | Live | End of phase 3 |
| `legacy/odoo-bas-sync/` | Daily Odoo `x_c21_listing` → BAS `properties-index` sync (Azure Function) | Azure Function App | Live | Keep while Genie searches `properties-index` |
| `legacy/property-chatbot/` | Staff Slack bot: property search over `properties-index`, CRM leads, contacts | App Service + Function App (RG `c21net-bas-property-chatbot-ea-prod`) | Live | End of phase 1 |
| `legacy/document-processor-notes/` | Loose planning notes and the Obsidian vault that sat beside the document processor | — | Reference | — |
| `shared/` | BAS 2.0 database schema: Supabase migrations, isolation test. See `shared/README.md`. | Supabase project `genie` (`xhaqzwznduxoosqtcrrm`) | Step 1 done | — |
| `portal/` | Genie sign-up and workspace admin (Next.js 16 + Supabase Auth). See `portal/README.md`. | Vercel project `nextjs-dashboard` (team Infinity Duo Technology) → **genie.infiniduo.com**, Root Directory `portal` | Step 2 in progress | — |
| `sync/`, `documents/`, `outbound/` | Reserved for BAS 2.0 parts that move out of the portal later. The live Odoo reader, MCP server and agent currently live in `portal/` (`lib/odoo`, `lib/mcp`, `lib/ai`). | Supabase + Vercel | Empty | — |

**Not in this repo, on purpose:**
- `c21-leasing` (www.c21net.com) — the public website; different audience and lifecycle.
- `bas-stacks` — another developer's project; reference only, never copy code without their agreement.
- `knowledge-sync-client` — lives in the `c21net` GitHub org; ownership not yet confirmed.

## Branches

- BAS 2.0 work: one branch per build step under `bas2/` — `bas2/shared-schema`, `bas2/portal`,
  `bas2/sync`, `bas2/outbound`, `bas2/web-chat`, ... Create each from the latest `main` when the
  step starts; merge to `main` by pull request when it is done.
- **Claude merges its own PRs (user decision 2026-10-16)** — the user does not want to merge each one.
  Flow: branch → PR → `npx tsc --noEmit`, `npm run lint`, `npm run build` pass → `gh pr merge --merge
  --delete-branch` → wait for the Vercel status on `main` to be `success` → tell the user what is live and
  what to test. Allowed by `Bash(gh pr merge *)` in `.claude/settings.local.json`.
- Fixes to old projects: `legacy/<short-description>`, e.g. `legacy/fix-chatbot-search`.

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
| genie-dashboard | lojul/property-intelligence-dashboard | `~/Active Projects/document processor/nextjs-dashboard` | Replaced, not switched: the Vercel project now builds `portal/` from `lojul/bas2`. Archive the old repo |
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
