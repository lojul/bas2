# bas2: one repository for Genie (BAS 2.0) and C21 document processing

This repository holds every project we own in the document-processing / property-AI area, so there is one place
to look. Created on 2026-10-08 by importing the existing repositories with their full git history.

**Start here: [`docs/genie/README.md`](docs/genie/README.md)**: Genie design docs (product, architecture, data and
security, Odoo changes, roadmap, operations). Current status and open items: [`docs/genie/status.md`](docs/genie/status.md).
Decisions with reasons: [`docs/genie/decisions.md`](docs/genie/decisions.md).
What changed when: [`CHANGELOG.md`](CHANGELOG.md).

## Genie in brief

Genie (genie.infiniduo.com, sold by Infinity Duo Technology) is the AI layer over a company's own data. Staff ask on
web, Slack or WhatsApp; outside AI agents use Genie's MCP server. Live, first workspace: C21.

Decisions to respect in every change (reasons in `docs/genie/decisions.md`):
- **No copy of customer data.** Read the customer's systems live at question time. Genie stores only accounts,
  workspaces, members, connection details, keys (Vault) and usage. Exceptions: saved chats (90 days), Odoo change
  drafts (values ≤ 24 h, who/what/which record 1 year) and WhatsApp memory (30 minutes). Any new exception needs the user's decision.
- **The customer's system stays the system of record.** Changes in Odoo are drafts a person confirms; off by default.
- **Multi-tenant on Supabase** (`genie`, ref `xhaqzwznduxoosqtcrrm`, Singapore): `tenant_id` on every row,
  row-level security on every table. Customer keys only in Vault, never in tables or code.
- **Odoo is optional**: no connector is mandatory. Odoo 19/20 via the JSON-2 API.
- **AI**: workspace's own key (Anthropic → OpenRouter → xAI) or the platform OpenRouter key. The platform account is
  registered in Hong Kong, so no Claude/GPT/Gemini on it (Qwen default).
- **The product name lives only in `portal/lib/brand.ts`.**
- Don't copy C21's live contacts, owners or listings into demos (PDPO).

## Workspaces (live)

Each workspace has its **own** set-up: Odoo, keys, Twilio account, Sandbox. Nothing is shared between them.

| Slug | Odoo | WhatsApp (Twilio) |
|---|---|---|
| `c21` | C21's Odoo (same key for reading and writing) | Twilio account "My first Twilio account", SID `ACbfa5…`, Sandbox +14155238886 |
| `infiniduo` | `https://admin-c21net-infiniduo.odoo.com` (Odoo 20, database `admin-c21net-infiniduo-main-40256688`, also at `…-main-40256688.dev.odoo.com`). Reads with an **MCP-scoped key** (source kind `odoo_mcp`), writes with an RPC key (`odoo_write_key`). Odoo user Julian (uid 5) | Its own Twilio login (julianlau@infiniduo.com), account "My First Twilio Account", SID `ACb426…`; Sandbox on (join phrase `join orange-minute`), webhook → `/api/whatsapp/infiniduo/inbound` (set 2026-10-21); SID + Auth Token saved in Genie and WhatsApp switched on (2026-10-24). Changes in Odoo on. Next: a **HK mobile number** (new SIM, registered as a Twilio WhatsApp sender) |

## Working notes for Claude

- Local `npm run build` needs env values: run it with placeholders from `portal/.env.example` (Vercel's build uses the real ones).
- `gh pr create`: pass the body with `--body-file` (an apostrophe inside `$(cat <<'EOF' …)` breaks the shell).
- Writing to `genie` through the Supabase MCP (e.g. creating a workspace for the user): `set_tenant_secret` needs
  `select set_config('request.jwt.claims', '{"role":"service_role"}', true);` in the same transaction.
- In a browser Claude can't type passwords or keys, and installing Odoo apps / changing user rights is left to the user.
- The claude.ai "Twilio" connector is Twilio's docs server (`mcp.twilio.com/docs`), not account access; use the
  Twilio console in Chrome.
- Odoo's MCP server (`/mcp`) has read tools only (search, read_group, fields, models); its key is refused by JSON-2.
- Applying a migration without the Supabase MCP: open the SQL Editor
  (`supabase.com/dashboard/project/xhaqzwznduxoosqtcrrm/sql/new`) in Chrome (the user signs in), set the text with
  `window.monaco.editor.getModels()[0].setValue(sql)`, click Run, and add the `schema_migrations` row
  (`shared/README.md`). Apply it **before** merging code that uses the new columns.
- The Chrome extension can't act on twilio.com pages (no site permission), but it can read the page text and URL
  (the URL holds the Account SID). The user pastes Auth Tokens.
- Genie on WhatsApp: linked members only; changes in Odoo by replying YES / NO; 30-minute memory (`whatsapp_turns`).

## Which folder to use

| Folder | What it is | Deploys to | Status | Retires at |
|---|---|---|---|---|
| `portal/` | **Genie**: sign-up, workspaces, Ask, agent, MCP server, Slack/WhatsApp, Odoo reader and changes (Next.js 16 + Supabase). See `portal/README.md` | Vercel project `nextjs-dashboard` (team Infinity Duo Technology) → **genie.infiniduo.com**, Root Directory `portal` | Live | — |
| `shared/` | Genie database: Supabase migrations, isolation test. See `shared/README.md` | Supabase project `genie` | Live | — |
| `docs/genie/` | Genie design docs, status, decisions, research | — | — | — |
| `sync/`, `documents/`, `outbound/` | Reserved for parts that may move out of the portal later | — | Empty | — |
| `legacy/document-processor/` | Document ingest: WhatsApp / Slack / Teams / OneDrive → OCR → classify → extract → Odoo. Python, LangGraph. Own `CLAUDE.md` | App Service `c21net-bas-api-doc-pipeline-ea-prod` + Function App `c21net-bas-func-doc-pipeline-ea-prod` (`./deploy.sh`) | Live | When the document add-on is rebuilt in Genie |
| `legacy/n8n/` | n8n workflow exports (WhatsApp/Slack glue). **Keys redacted**, see Secrets | n8n | Live | Same |
| `legacy/odoo-bas-sync/` | Daily Odoo `x_c21_listing` → `properties-index` sync (Azure Function) | Azure Function App | Live | Keep while Genie searches `properties-index` |
| `legacy/property-chatbot/` | Old staff Slack bot (fallback if C21's Slack app is pointed back) | App Service + Function App (RG `c21net-bas-property-chatbot-ea-prod`) | Live | Once Genie's Slack is confirmed |
| `legacy/genie-dashboard/` | Old web dashboard, replaced by `portal/` | — | Retired | Delete |
| `legacy/document-processor-notes/` | Loose planning notes and an Obsidian vault | — | Reference | — |

Switch-over status of the legacy projects and syncing their copies: [`legacy/README.md`](legacy/README.md).

**Not in this repo, on purpose:** `c21-leasing` (www.c21net.com, the public website); `bas-stacks` (another
developer's project: reference only, never copy code without their agreement); `knowledge-sync-client` (in the
`c21net` GitHub org, ownership not confirmed).

## Branches and merging

- Genie work: a branch per change under `bas2/…`, created from the latest `main`, merged by pull request.
- **Claude merges its own PRs (user decision 2026-10-16).** Flow: branch → PR → `npx tsc --noEmit`, `npm run lint`,
  `npm run build` (in `portal/`) pass → `gh pr merge --merge --delete-branch` → wait for the Vercel status on `main`
  to be `success` → tell the user what is live and what to test. Allowed by `Bash(gh pr merge *)` in
  `.claude/settings.local.json`.
- Fixes to old projects: `legacy/<short-description>`, e.g. `legacy/fix-chatbot-search`.

## Rules

- `legacy/` gets fixes only, no new features. New work goes into the Genie folders.
- Delete a `legacy/` folder only when its Genie replacement has passed its gate.
- Never commit `.env`, `local.settings.json` or keys (see `.gitignore`). Legacy secrets live in Azure app settings /
  Key Vault; Genie customer keys live in Supabase Vault.
- Keep the docs current: when a change ships, add a line to `CHANGELOG.md`, update `docs/genie/status.md` (and the design doc it affects); record
  new decisions in `docs/genie/decisions.md`, not in this file.

## Secrets

The n8n exports in `legacy/n8n/` contained live keys (OpenRouter, Azure OpenAI, Document Intelligence, Azure Search,
Odoo, PDF.co, and a blob SAS token valid until 2028-03-31). They are replaced with `REDACTED` here. The unredacted
originals are still in `~/Active Projects/document processor/n8n/` (never pushed). Rotating those keys is
recommended.
