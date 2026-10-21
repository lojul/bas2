# 3. Data and security

[← Architecture](2-architecture.md) · next: [Changes in Odoo →](4-odoo-changes.md)

## What Genie keeps, and what it never keeps

```mermaid
flowchart LR
    subgraph KEEP["✅ Kept in Genie"]
        direction TB
        K1["Accounts, workspaces, members, roles"]
        K2["Connection details<br/>(address, settings)"]
        K3["Keys: encrypted in Vault"]
        K4["Usage counts<br/>(messages, tokens, tool calls)"]
        K5["Saved chats<br/>90 days after last message"]
        K6["Odoo change log: who, what, which record<br/>draft values ≤ 24 h, log 1 year"]
    end
    subgraph NEVER["⛔ Never kept"]
        direction TB
        N1["Odoo records<br/>contacts, leads, listings"]
        N2["Documents and their text"]
        N3["Search indexes over customer data"]
    end
    K1 ~~~ K2 ~~~ K3 ~~~ K4 ~~~ K5 ~~~ K6
    N1 ~~~ N2 ~~~ N3
    KEEP ~~~ NEVER
```

Everything in "Never kept" stays in the customer's own systems and is read live when someone asks.

Saved chats can quote customer data in Genie's answers. That's why they are deleted automatically and the
privacy policy names them.

### How long things are kept

| Data | Kept for | Removed by |
|---|---|---|
| Saved chats and their messages | 90 days after the last message, or until deleted by the author / an owner or admin | pg_cron `genie-chat-retention`, daily 03:00 HKT |
| Odoo draft values | Until decided, at most 24 hours | pg_cron `genie-odoo-actions-cleanup`, hourly |
| Odoo change log (who, what, which record) | 1 year | Same job |
| Invite links | 7 days, single use, renewable | Expiry check |
| WhatsApp messages, Slack threads | Not stored (Slack history is read back from Slack) | — |

## Data model

```mermaid
erDiagram
    TENANTS ||--o{ TENANT_MEMBERS : "has"
    USERS ||--o{ TENANT_MEMBERS : "belongs to"
    TENANTS ||--o{ INVITATIONS : "sends"
    TENANTS ||--o{ SOURCES : "connects"
    TENANTS ||--o{ TENANT_SECRETS : "owns keys"
    TENANTS ||--o{ API_KEYS : "issues"
    TENANTS ||--o{ CHATS : "holds"
    CHATS ||--o{ CHAT_MESSAGES : "contains"
    TENANTS ||--o{ ODOO_ACTIONS : "logs"
    CHATS |o--o{ ODOO_ACTIONS : "drafted in"
    TENANTS ||--o{ USAGE_EVENTS : "meters"
```

| Table | Holds | Who can see it |
|---|---|---|
| `tenants` | A workspace: name, slug, plan, `settings` (AI model choice, channels, Odoo-change switches) | Members read; owner/admin update |
| `tenant_members` | User ↔ workspace, with role | Members read; owner/admin manage |
| `invitations` | Email, role, **token hash**, expiry, accepted date | Owner/admin |
| `sources` | Connected systems: kind (`odoo_json2`, `azure_search`…), non-secret settings, status | Members read; owner/admin manage |
| `tenant_secrets` | Key name and last 4 characters; **the value lives in Vault** | Owner/admin; values only via the server |
| `api_keys` | MCP keys, **hash only** | Owner/admin |
| `chats`, `chat_messages` | Saved Ask chats and messages | Team chat: members; private: author |
| `odoo_actions` | Drafted and made Odoo changes | Owner/admin, or the requester |
| `usage_events` | Metering for billing | Written by the server |
| `records`, `passages` | Old copy design, demo data only, not used for customers | — |

## How workspaces stay apart

There are **two paths** into the data, and they are protected differently:

```mermaid
flowchart TB
    R["Request"] --> I["Entry point checks who is asking<br/>Ask: session + membership of the workspace in the URL<br/>Slack / WhatsApp: signature checked with that workspace's secret<br/>MCP: key hash → its workspace"]
    I --> W["The entry point fixes the workspace<br/>(never taken from the browser body,<br/>the AI's tool arguments or the message text)"]
    W --> U
    W --> S

    subgraph USER["Member path"]
        U["User's own Supabase session"] --> L["Row-level security<br/>Postgres checks membership<br/>on every row"]
    end

    subgraph SRV["Server path"]
        S["Service-role client<br/>(SUPABASE_SECRET_KEY)<br/>⚠ bypasses row-level security"] --> K["Sources and keys of the<br/>workspace it was given<br/>e.g. liveSourcesFor(tenantId)"]
    end

    L --> DB[("Genie database")]
    K --> C[("That workspace's<br/>own Odoo / index")]
```

- **Member path.** Pages, chats and settings read the database as the signed-in user. Row-level security is on every
  table (policies use `private.is_member`, `private.has_role`, `private.can_see_chat`), so a wrong workspace id
  returns nothing.
- **Server path.** Reading sources and Vault keys for live calls (`portal/lib/live.ts`), Slack/WhatsApp/MCP
  requests (no signed-in user), Odoo writes, and writing Genie's answers and usage all use the service-role client.
  **Row-level security does not apply there.** The only guard is that the entry point resolved the right
  workspace; a bug that passes the wrong `tenantId` would read another workspace's sources and keys. Every
  service-role call must therefore take its workspace from the entry point's identity check, and filter by it.
  Making this a tested rule is [platform hardening item 4](5-roadmap.md#platform-hardening).
- **Isolation test:** `shared/supabase/tests/isolation_test.sql` creates test workspaces and checks they can't see
  each other. It is run by hand today; running it on every release is on the [roadmap](5-roadmap.md#platform-hardening).

## Keys

| Key | Kept in | Who can see it |
|---|---|---|
| Customer keys (Odoo reading and writing, search, AI, Slack, Twilio) | Supabase Vault | Owners/admins can reveal one on click (`reveal-action.ts`); the server reads them for live calls |
| MCP keys `gnk_…` | Hash only | Nobody, not even owners; revoke and make a new one |
| Platform keys (`SUPABASE_SECRET_KEY`, `OPENROUTER_API_KEY`) | Vercel, marked Sensitive | Server only, never `NEXT_PUBLIC_` |

Odoo reading and writing use **separate keys** on purpose, so a dedicated "Genie" Odoo user can be given write
access without touching reading.

## Sign-in and invites

- Email + password through Supabase Auth; Google and Microsoft are set up but shown as "coming soon".
- Invites are single-use links (only the hash is stored), valid 7 days. Until email sending exists,
  **a held link works like a key**: whoever has it can join. Emailed invites with a code are on the roadmap.

## Known gaps

| Gap | Fix planned |
|---|---|
| Isolation test is manual, and covers row-level security only | Run on every PR, including the service-role path through each entry point ([roadmap](5-roadmap.md#platform-hardening)) |
| The change log is an ordinary table that the server could edit | Tamper-evident log ([roadmap](5-roadmap.md#platform-hardening)) |
| Invite link = key | Emailed invites with a 6-digit code |
| Anyone who can message the Slack bot or the WhatsApp number can ask | Link members to their Slack user / phone |
