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

Every request passes the same layers. A mistake in one layer is caught by the next.

```mermaid
flowchart LR
    R["Request"] --> I["<b>Step 1</b><br/>Who is asking?<br/>session · Slack/Twilio signature ·<br/>MCP key hash"]
    I --> W["<b>Step 2</b><br/>Server picks the workspace<br/>from that identity, never<br/>from the browser or the AI"]
    W --> L["<b>Step 3</b><br/>Row-level security:<br/>every row has tenant_id,<br/>Postgres checks membership"]
    L --> K["<b>Step 4</b><br/>Workspace's own key<br/>read from Vault"]
    K --> C[("That customer's<br/>own system")]
```

- **Row-level security** is on every table. Policies use `private.is_member`, `private.has_role` and
  `private.can_see_chat`.
- **The server's secret key** (`SUPABASE_SECRET_KEY`) is used only on the server: to read keys for live calls, to
  handle Slack/WhatsApp/MCP requests that have no signed-in user, and to write Genie's answers and usage.
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
| Isolation test is manual | Run on every PR ([roadmap](5-roadmap.md#platform-hardening)) |
| The change log is an ordinary table that the server could edit | Tamper-evident log ([roadmap](5-roadmap.md#platform-hardening)) |
| Invite link = key | Emailed invites with a 6-digit code |
| Anyone who can message the Slack bot or the WhatsApp number can ask | Link members to their Slack user / phone |
