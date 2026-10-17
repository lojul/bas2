# Genie (BAS 2.0) — concept and technical overview

Status as of 2026-10-17. Live at **https://genie.infiniduo.com**. Detailed build notes: `portal/README.md`;
decisions and build order: root `CLAUDE.md`.

---

## Part 1 — Concept

**Genie is one assistant that answers questions from a company's own systems, wherever its staff already work.**

| | |
|---|---|
| **Who uses it** | Staff of a company (e.g. C21's property agents), and outside AI apps the company allows |
| **Where they ask** | Web (Ask) · Slack · WhatsApp · Claude / ChatGPT / own agents (through Genie's MCP server) |
| **What it reads** | The company's own systems, **live at the moment of the question**: Odoo, the company's own Azure AI Search document index. SQL databases next |
| **What it stores** | Accounts, workspaces, members, connection details, encrypted keys (Vault), usage counts — and **saved chats (90 days)**. **Never a copy of the company's records** |
| **AI** | A model gateway: the company's own AI key (Anthropic, OpenRouter, xAI) or Genie's platform key; the model is chosen per workspace |
| **Sold as** | Multi-company subscription (Starter / Business / Enterprise + Document add-on) by Infinity Duo Technology — billing not built yet |

### The principles

1. **Read live, don't copy.** Answers are always current, and "we keep no copy of your data" is a selling point
   (PDPO). The one agreed exception: chats people save on Ask, deleted 90 days after the last message.
2. **The customer's system stays the system of record.** Genie reads; changes (create lead/contact, note, follow-up, allowed field updates) only as drafts a person confirms on Ask, switched off by default.
3. **Self-service setup.** A workspace owner connects sources and channels in Settings: an on/off card each,
   Save, Test connection, keys masked with show/copy.
4. **Plain business software look.** ERPNext / Frappe-desk style; Ask in Microsoft Copilot style.

### How people move around

```
User (sign in: email + password; Google/Microsoft "coming soon")
 └─ Workspace (one per company; most people have one and go straight in)
     ├─ Ask        ← home: new chat, team chats (👥, Genie answers on @Genie), private chats (🔒)
     ├─ Team       ← invite by link (invitee sets a password on the link), roles, invitation history
     ├─ Settings   ← Data sources · AI model keys · AI agent access (MCP) · Channels
     └─ Help
```

Account menu (top right): your workspaces (switch / new), change password, help, sign out.
Roles: **Owner** (everything) · **Admin** (members, sources, keys) · **Member** (asks) · **Viewer** (read-only).

### What C21's workspace has today

| Part | State |
|---|---|
| Odoo `c21net.odoo.com` | On — contacts, CRM leads, listings, read live |
| C21 documents (Azure AI Search `properties-index`, ~5,700 SharePoint files) | On — searched live with read-only key `genie-readonly` |
| Slack (`@c21_property_chatbot`, Slack workspace C21net) | Connected — same bot as before, now answered by Genie |
| WhatsApp (Twilio Sandbox +1 415 523 8886) | Connected — text → Genie; photos/files → C21's n8n document intake |
| Members | 2 |

### Known limits (honest list)

- Not yet proven with real use — a one-week trial with C21 agents is the next step.
- Search inside Odoo is keyword search; differently worded questions can miss.
- The platform AI account is registered in Hong Kong → no Claude / GPT / Gemini on it (Qwen is the default);
  a workspace's own key lifts this.
- Changes in Odoo work on Ask only (Slack/WhatsApp still read-only), and need a dedicated Genie Odoo user.
- WhatsApp is the Twilio Sandbox (test only, ~50 messages/day, no memory between messages).
- No outgoing email yet (invites are links you send yourself; anyone holding an invite link can use it).
- No billing yet.

### What to add next (by value)

| # | Add-on | Why |
|---|---|---|
| 1 | Actions in Odoo from chat (create lead/contact, log viewing) | Agents act from WhatsApp/Slack — biggest time saver |
| 2 | Answer quality: Odoo-wins rule and fixed layout; vector search on C21's index | Trust |
| 3 | Email sending (Resend): emailed invites with a code, password reset for everyone | Security, onboarding |
| 4 | Stripe plans and limits; usage page | First paying customer |
| 5 | Document add-on (flyer/photo → Odoo), rebuilt into Genie | Premium upsell, proven at C21 |
| 6 | More live sources (SQL, SharePoint/Drive search), Teams, real WhatsApp number | Sell beyond Odoo users |

---

## Part 2 — Technical

### Architecture

```
 Staff: Web (Ask)   Slack     WhatsApp (Twilio)    Outside AI agents (MCP)
          │           │             │                      │
          ▼           ▼             ▼                      ▼
 ┌──────────────────── portal/ (Next.js 16, Vercel, functions in sin1) ───────────────────┐
 │ app/app/[slug]/ask   api/slack/[slug]/events   api/whatsapp/[slug]/inbound   api/mcp  │
 │        └───────────────┬──────────┴──────────────────┘                        │       │
 │                 lib/ai/agent.ts  (askAgent: prompt + tools + metering)       │       │
 │                        │                                                     │       │
 │        lib/ai/gateway.ts  (own key → platform OpenRouter; model per workspace)│       │
 │                        │                                                     │       │
 │                lib/live.ts  (switched-on sources → tools) ◄──────────────────┘       │
 │                 │                          │                                         │
 │        lib/odoo/live.ts             lib/search/azure.ts                               │
 └─────────────────┼──────────────────────────┼─────────────────────────────────────────┘
                   ▼                          ▼
          Customer's Odoo (JSON-2)   Customer's Azure AI Search index
                   (read live, nothing copied)

 Supabase project "genie" (ap-southeast-1): Postgres + RLS · Auth · Vault · Realtime · pg_cron
```

### Stack

| Part | Choice |
|---|---|
| Web app | Next.js 16 (App Router, server actions), Tailwind, Inter; `portal/` |
| Hosting | Vercel project `nextjs-dashboard` (team Infinity Duo Technology), domain genie.infiniduo.com, functions pinned to **sin1** (`portal/vercel.json`) |
| Database / auth | Supabase `genie` (ref `xhaqzwznduxoosqtcrrm`, Singapore): Postgres with row-level security on every table, Supabase Auth, Vault for keys, Realtime for chats, pg_cron for retention |
| AI | Anthropic SDK (own Anthropic key) or OpenAI-compatible chat completions (OpenRouter / xAI); OpenRouter gets a model list with fallbacks and `data_collection: deny` |
| Migrations | `shared/supabase/migrations/` (applied to `genie`) |

### One question, end to end

1. A message arrives: Ask server action (`postMessage`), Slack event, Twilio webhook, or MCP tool call.
2. Channel checks: signed-in member (web) · Slack HMAC signature · Twilio HMAC-SHA1 signature · MCP API key hash.
3. `askAgent` builds the prompt (names the switched-on sources), offers only tools that can work, and runs the
   tool loop through the gateway (lookups in one step run in parallel).
4. Tools read the customer's systems live (`runLiveTool`): `search_records`, `get_record`, `find_contact` → Odoo;
   `search_knowledge` → the document index.
5. The answer goes back (Ask: saved to the chat; Slack: placeholder replaced; WhatsApp: Twilio Messages API).
6. Usage is metered in `usage_events` (message, input/output tokens, tool calls; channel).

### Data model (Supabase `public`)

| Table | Holds | Access |
|---|---|---|
| `tenants` | Workspace: name, slug, plan, `settings` (AI model choice, channels config) | members read; owner/admin update |
| `tenant_members` | User ↔ workspace with role | members read; owner/admin manage |
| `invitations` | Email, role, **token hash**, expiry, accepted date | owner/admin |
| `tenant_secrets` | Key metadata (+ last 4); the value lives in **Vault** | owner/admin; values only via service role |
| `sources` | Connected systems: kind (`odoo_json2`, `azure_search`, …), non-secret config, status | members read; owner/admin manage |
| `odoo_actions` | Drafted / made changes in Odoo: who, what, which record (draft values ≤24 h) | owner/admin, or the requester |
| `chats`, `chat_messages` | Saved Ask chats (team/private) and messages | team: members; private: author; Genie's messages written by the server |
| `api_keys` | MCP keys (**hash only**) | owner/admin |
| `usage_events` | Metering | service role writes |
| `records`, `passages` | Old copy design — only demo data; not used for customers | — |

### Security

- **Isolation:** every row carries `tenant_id`; RLS policies use `private.is_member` / `private.has_role` /
  `private.can_see_chat`.
- **Keys:** Supabase Vault; never in tables or code. Owners/admins can reveal one key on click
  (`reveal-action.ts`); MCP keys are hash-only and can't be revealed.
- **Service role** (`SUPABASE_SECRET_KEY`) only on the server: reading keys for live calls, Slack/WhatsApp/MCP
  requests that have no signed-in user, writing Genie's chat answers and usage.
- **Webhooks** verify signatures (Slack: HMAC-SHA256 + 5-minute window; Twilio: HMAC-SHA1, checked against the
  official `twilio` library).
- **Invites:** single-use token (hash stored), 7 days, renewable; invitee accounts are created confirmed because
  the link proves receipt — a held link is effectively a key until email sending exists.

### Code map (`portal/`)

| Path | What |
|---|---|
| `app/app/[slug]/ask` | Ask: chats (`chat-room.tsx`, `actions.ts`), setup strip |
| `app/app/[slug]/settings` + `sources/`, `keys/`, `agents/`, `channels/` | Settings tabs (`?tab=`) |
| `app/app/[slug]/members` | Team, invites, invitation history |
| `app/api/mcp`, `app/api/slack/[slug]/events`, `app/api/whatsapp/[slug]/inbound` | Outside entry points |
| `components/workspace-shell.tsx` | Top bar, sidebar (chats under Ask, data sources, channels), account menu |
| `components/secret-input.tsx` | Key fields with show/copy |
| `lib/ai/` | Agent, gateway, model options, tool definitions |
| `lib/live.ts`, `lib/odoo/`, `lib/search/` | Live sources |
| `lib/slack/`, `lib/whatsapp/` | Channel helpers |

### Operations

| Item | Detail |
|---|---|
| Deploy | Branch → PR → checks (`tsc`, `lint`, `build`) → Claude merges → Vercel deploys `main` (wait for `success`) |
| Env vars (Vercel) | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `NEXT_PUBLIC_SITE_URL`, `SUPABASE_SECRET_KEY`, `OPENROUTER_API_KEY`, optional `GENIE_OPENROUTER_MODEL` |
| Scheduled job | pg_cron `genie-chat-retention`, daily 03:00 HKT, deletes chats idle 90 days |
| Expiry to watch | Microsoft Entra client secret for sign-in: **2028-10-15** |
| Region notes | Functions in sin1; OpenRouter platform account in Hong Kong (model limits above) |
| Legacy dependencies | C21's `properties-index` is filled by legacy jobs — keep them running; old Slack bot Azure Function kept as fallback |
| Before the first paying tenant | Supabase Pro (free projects pause), email sending, Stripe, real WhatsApp number |
