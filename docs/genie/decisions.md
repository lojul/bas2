# Genie: decision log

[← Design docs](README.md)

Decisions that shape Genie, newest group first, with the reason. Change a decision by adding a new row, not by
editing an old one. Full early reasoning (connector catalogue, pricing): tab "SaaS, connectors and Odoo" in the
[BAS 2.0 plan](https://claude.ai/code/artifact/90d4a48f-0eab-4a0e-b01e-0fbfed1edef5).

## Data

| Date | Decision | Why / consequence |
|---|---|---|
| 2026-10-16 | **No copy of customer data.** "We don't store stuff in Genie, we should not." Genie stores only accounts, workspaces, members, connection details, encrypted keys (Vault) and usage counts | Answers are always current; a privacy selling point (PDPO). Dropped: scheduled sync, embedding index over customer data, CSV upload into Genie. The old `records` table holds only synthetic demo data. The document add-on needs a design that reads files where they live |
| 2026-10-17 | Exception 1: **saved chats** (`chats`, `chat_messages`), deleted 90 days after the last message, or earlier by the author / an owner or admin | Members share answers (Team chats). Privacy policy updated |
| 2026-10-17 | Exception 2: **Odoo change drafts**: values for ≤ 24 h, then only who / what / which record for a year | People confirm drafts; the log shows what Genie changed |
| 2026-10-16 | Saved keys can be shown and copied by owners/admins (MCP keys stay hash-only) | User request. Privacy policy updated |

## Product and platform

| Date | Decision | Why / consequence |
|---|---|---|
| 2026-10-15 | Working name **Genie** (genie.infiniduo.com); final name before public launch | The name lives only in `portal/lib/brand.ts`, so a rename is cheap. Shortlists parked in the plan doc |
| 2026-10-15 | Sold by **Infinity Duo Technology**: multi-tenant SaaS, Starter / Business / Enterprise + Document add-on | Stripe account exists (test mode). Document → Odoo/SQL field mapping is quoted customisation only |
| 2026-10-15 | **Supabase** (Postgres, Auth, Vault, Realtime, pg_cron), one shared schema, `tenant_id` on every row, row-level security; region ap-southeast-1 (Singapore) | Closest region to HK; isolation enforced by the database |
| 2026-10-15 | `portal/` replaces the old genie dashboard at genie.infiniduo.com; C21 gets a workspace in it | One product, not two |
| 2026-10-15 | **Odoo is optional**; no connector is mandatory. Odoo 19/20 through the JSON-2 API; XML-RPC (Odoo 18 and older) only if a paying customer needs it | Sell beyond Odoo users. XML-RPC is deprecated since Odoo 19 |
| 2026-10-21 | Odoo can also be connected with an **MCP-scoped key** (Odoo 20 "Scope: MCP"): Genie reads through Odoo's `/mcp` tools (search, count, field list); source kind `odoo_mcp` | User request for Infinity Duo's workspace (no RPC key). Reading uses the MCP key; Changes in Odoo use a separate key with Scope "RPC" (JSON-2), as for any workspace (Odoo's MCP server has no write tools). `connect` tries JSON-2, then MCP, then the older API |
| 2026-10-15 | Genie doesn't depend on C21: C21 joins as an ordinary workspace by connecting its own Odoo; no C21 data is copied into our systems or demos | C21 is the first live workspace (2026-10-16). Don't copy C21's contacts, owners or listings into a demo (PDPO); reuse C21 flyers/floor plans only with C21's written OK |
| 2026-10-15 | Meter messages, tokens, tool calls (and later OCR pages) per workspace from day one; Stripe Billing + customer portal | Billing can start without a data backfill |

## AI

| Date | Decision | Why / consequence |
|---|---|---|
| 2026-10-15 | Bring-your-own key (Anthropic, OpenRouter, xAI, Azure OpenAI) through one gateway; Genie's platform key as the default | Customers can use their own AI contract |
| 2026-10-15 | Platform key is **OpenRouter only**; no platform Anthropic key | — |
| 2026-10-16 | The OpenRouter account is registered in Hong Kong, so Anthropic, OpenAI and Google refuse it (403). Fallback list: `GENIE_OPENROUTER_MODEL`, then Qwen 3.8 Max, DeepSeek V4 Pro, GLM 5.3, with `data_collection: deny` | Claude for C21 needs a workspace's own Anthropic key or a non-HK platform account |
| 2026-10-16 | Model chosen per workspace (Settings → AI model keys) | — |

## Odoo changes

| Date | Decision | Why / consequence |
|---|---|---|
| 2026-10-17 | Changes in Odoo off by default; every change is a draft the requester or an owner/admin confirms; web only for now | The AI can misread a request |
| 2026-10-17 | Writes use their own Vault key (`odoo_write_key`), separate from the reading key | A dedicated Genie Odoo user can get write rights without touching reading. C21 has one Odoo user, so the same key is pasted into both for now |

## Sign-in and look

| Date | Decision | Why / consequence |
|---|---|---|
| 2026-10-16 | Email sign-in links dropped; email + password with forgot-password | The PKCE link flow failed on the live site |
| 2026-10-17 | Google and Microsoft sign-in set up but shown as "Coming soon" (`SOCIAL_SIGNIN_READY` in `portal/lib/auth-settings.ts`) | Switch on when ready; Google consent screen still in Testing mode |
| 2026-10-16 | ERPNext / Frappe-desk look, 16px base; Ask in Microsoft Copilot style as the home page (Overview removed) | User request |

## Demo data (proposed, to confirm)

| Date | Decision | Why / consequence |
|---|---|---|
| 2026-10-15 | Demo A (property): our own Odoo 20 with Odoo's demo CRM/contacts plus a listing model shaped like C21's `x_c21_listing`, ~200 synthetic listings (real public building names and districts; invented units, prices, owners, phones). Demo B (generic SME): a small Postgres sample database | Shows Odoo is optional. Needs an Odoo 20 environment and an integration user's API key |
| 2026-10-16 | Demo B (*Harbour Supplies*) deleted from `genie` at the user's request | The seed stays at `shared/supabase/seed/demo_tenant_b.sql` for when a demo is needed again |

## WhatsApp

| Date | Decision | Why / consequence |
|---|---|---|
| 2026-10-21 | Genie answers WhatsApp text **only from numbers linked to a member** (member sends "LINK <code>" from the phone; code hash only, 10 minutes). Photos/files keep going to the workspace's document intake unchanged | Anyone who knew the number could read the workspace's data. Links are needed for changes in Odoo from WhatsApp (next step). The member's phone number is Genie account data, not customer data |
| 2026-10-21 | **Each workspace has its own channel set-up** (Twilio account, Sandbox, keys); nothing is shared between workspaces, e.g. C21 and Infinity Duo | User decision |
| 2026-10-17 | Each customer uses **its own WhatsApp number**, never one shared "Genie" number | Meta bars general-purpose AI chatbots; task-bound bots over a company's own data are fine. See [research](research/whatsapp.md) |
