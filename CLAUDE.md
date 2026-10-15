# bas2 — one repository for C21 document processing and BAS 2.0

This repository holds every project we own in the document-processing / property-AI
area, so there is one place to look. It was created on 2026-10-08 by importing the
existing repositories with their full git history (no code changes).

Plan for BAS 2.0 (one-page summary, architecture, document add-on, implementation plan):
https://claude.ai/code/artifact/90d4a48f-0eab-4a0e-b01e-0fbfed1edef5

## Which folder to use

| Folder | What it is | Deploys to | Status | Retires at |
|---|---|---|---|---|
| `legacy/document-processor/` | Document ingest: WhatsApp / Slack / Teams / OneDrive → OCR → classify → extract → Odoo. Python, LangGraph. Has its own detailed `CLAUDE.md`. | App Service `c21net-bas-api-doc-pipeline-ea-prod` + Function App `c21net-bas-func-doc-pipeline-ea-prod` (`./deploy.sh`) | Live | End of BAS 2.0 phase 3 |
| `legacy/genie-dashboard/` | Web dashboard at genie.infiniduo.com (Next.js, Vercel) | Vercel (currently built from the old GitHub repo, see Switch-over) | Live | Becomes `portal/` in phase 4 |
| `legacy/n8n/` | n8n workflow exports (WhatsApp/Slack glue). **Keys redacted** — see Secrets | n8n | Live | End of phase 3 |
| `legacy/odoo-bas-sync/` | Daily Odoo `x_c21_listing` → BAS `properties-index` sync (Azure Function) | Azure Function App | Live | End of phase 1 |
| `legacy/property-chatbot/` | Staff Slack bot: property search over `properties-index`, CRM leads, contacts | App Service + Function App (RG `c21net-bas-property-chatbot-ea-prod`) | Live | End of phase 1 |
| `legacy/document-processor-notes/` | Loose planning notes and the Obsidian vault that sat beside the document processor | — | Reference | — |
| `sync/`, `documents/`, `outbound/`, `portal/`, `shared/` | BAS 2.0 projects (bas2-sync, bas2-documents, bas2-outbound, bas2-portal, shared storage schema) | — | Not started | — |

**Not in this repo, on purpose:**
- `c21-leasing` (www.c21net.com) — the public website; different audience and lifecycle.
- `bas-stacks` — another developer's project; reference only, never copy code without their agreement.
- `knowledge-sync-client` — lives in the `c21net` GitHub org; ownership not yet confirmed.

## Rules

- `legacy/` gets fixes only, no new features. New work goes into the BAS 2.0 folders.
- Delete a `legacy/` folder only when its BAS 2.0 replacement has passed its gate.
- Never commit `.env`, `local.settings.json` or keys (see `.gitignore`). Secrets live in Azure app settings / Key Vault.
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

The `legacy/` copies are frozen at 2026-10-08 and do not include these. Read the old
repo for the current code and docs:

| Date | Project | Change | Where to read |
|---|---|---|---|
| 2026-10-15 | document-processor | New upload channel: Odoo **C21 放盤管理 → 文件上傳**. A staff upload in Odoo triggers a webhook to `POST /api/odoo/upload`, the file goes through the same pipeline as WhatsApp/Slack, and the result is written back to the Odoo record. The Odoo side is built with Studio-compatible records (model `x_c21_doc_upload`) by `scripts/setup_odoo_doc_upload.py`. | lojul/c21-document-processor, `CLAUDE.md` (UPDATE 2026-10-15), commits `63b0e92`, `5a2bbf5`, `c956e1a`. Live since 2026-10-15. |

To switch one: recreate its virtualenv / `node_modules` inside this repo, deploy once
from here and verify behaviour, then archive the old GitHub repo with a README pointing here.

## Secrets

The n8n exports in `legacy/n8n/` contained live keys (OpenRouter, Azure OpenAI,
Document Intelligence, Azure Search, Odoo, PDF.co, and a blob SAS token valid until
2028-03-31). They are replaced with `REDACTED` here. The unredacted originals are
still in `~/Active Projects/document processor/n8n/` (never pushed). Rotating those
keys is recommended.
