# legacy/: the projects imported into bas2

These folders were imported on 2026-10-08 from their own repositories with full git history (no code changes).
They get **fixes only, no new features**. Delete a folder only when its Genie replacement has passed its gate.
Which folder is what, and where it deploys: root [`CLAUDE.md`](../CLAUDE.md) → Which folder to use.

## Switch-over status

The old repositories still exist and are still what deployments use. Until a row says "Yes", the old location is the
source of truth and the copy here is a snapshot.

| Project | Old GitHub repo | Old local folder | Switched to bas2? |
|---|---|---|---|
| document-processor | lojul/c21-document-processor | `~/Active Projects/document processor/langgraph` | No |
| genie-dashboard | lojul/property-intelligence-dashboard | `~/Active Projects/document processor/nextjs-dashboard` | Replaced, not switched: the Vercel project now builds `portal/` from `lojul/bas2`. Archive the old repo |
| odoo-bas-sync | lojul/odoo-bas-sync | `~/Active Projects/odoo-bas-sync` | No |
| property-chatbot | lojul/c21-property-chatbot | `~/Active Projects/c21-property-chatbot` | No |

To switch one: recreate its virtualenv / `node_modules` inside this repo, deploy once from here and verify
behaviour, then archive the old GitHub repo with a README pointing here. After switching, stop editing the old local
folder (one copy only).

## Changes made in the old repos after the import

Changes are made and deployed from the old repos. The copy here is refreshed afterwards with `git subtree pull`
(history kept), e.g. `git subtree pull --prefix=legacy/document-processor "<old local folder>" master`.

| Date | Project | Change | Copy here up to date? |
|---|---|---|---|
| 2026-10-15 | document-processor | New upload channel: Odoo **C21 放盤管理 → 文件上傳**. A staff upload in Odoo triggers a webhook to `POST /api/odoo/upload`, the file goes through the same pipeline as WhatsApp/Slack, and the result is written back to the Odoo record. The Odoo side is built with Studio-compatible records (model `x_c21_doc_upload`) by `scripts/setup_odoo_doc_upload.py`. Live since 2026-10-15. Details: `legacy/document-processor/CLAUDE.md` (UPDATE 2026-10-15) | Yes, synced to old repo commit `c956e1a` |
