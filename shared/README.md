# shared/ — BAS 2.0 (Genie) database schema

The Supabase schema every BAS 2.0 project builds on: tenants, users and roles, row-level
security, per-tenant secrets in Supabase Vault, the synced-data and vector store, usage
metering, and the private `documents` storage bucket.

| | |
|---|---|
| Supabase project | `genie` — ref `xhaqzwznduxoosqtcrrm`, region ap-southeast-1 (Singapore), free tier |
| Dashboard | https://supabase.com/dashboard/project/xhaqzwznduxoosqtcrrm |
| Migrations | `supabase/migrations/` — applied in filename order |
| Isolation test | `supabase/tests/isolation_test.sql` |

## The model in one page

- **Every tenant-owned row has `tenant_id`.** Row-level security is on for every table.
  Policies call helpers in the `private` schema (`is_member`, `has_role`, `my_tenant_ids`),
  which is not exposed through the Data API.
- **Roles** (`member_role`): `owner` > `admin` > `member` > `viewer`. Owners manage everyone;
  admins manage non-owners, sources, invitations and secrets; members read and upload documents;
  viewers read only. A tenant always keeps at least one owner.
- **Same-tenant foreign keys.** References between tenant tables are composite
  (`(x_id, tenant_id)`), so a row can never point at another tenant's source, secret,
  record or document, even if someone guesses its id.
- **Who writes what.** Users (through the portal, with their own JWT) write `sources`,
  `documents`, `invitations`, `tenant_members`. Server code (service role) writes `records`,
  `chunks` and `usage_events`: sync workers, the embedding job, metering.

### Tables

| Table | Purpose | Signed-in users can |
|---|---|---|
| `tenants` | One row per customer company; plan, Stripe customer id, settings | read own; owner/admin update |
| `tenant_members` | User ↔ tenant with role | read colleagues; owner/admin manage |
| `invitations` | Pending invites (only the SHA-256 of the token is stored) | owner/admin |
| `tenant_secrets` | Name, provider and last-4 hint of each stored key; the value is in Vault | owner/admin read metadata |
| `sources` | One per connector (`sql`, `csv`, `odoo_json2`, `odoo_mcp`, ...), with non-secret config and field mapping | read; owner/admin manage |
| `records` | Read copy of the customer's data (listing, contact, lead, ...); `fts` and trigram indexes | read |
| `documents` | Uploaded files; bytes in Storage at `documents/<tenant_id>/...` | read; members upload; owner/admin edit |
| `chunks` | Text + 1536-dim embedding from a record or document; HNSW index | read |
| `usage_events` / `usage_monthly` | Metered messages, OCR pages, tokens, synced records (feeds Stripe) | owner/admin read |

### Functions (RPC)

| Function | Called by | Does |
|---|---|---|
| `create_tenant(name, slug)` | signed-in user | creates a tenant and makes the caller its owner |
| `accept_invitation(token)` | signed-in user | joins the tenant if the token matches a pending invite for the caller's email |
| `set_tenant_secret(tenant, name, kind, provider, secret)` | owner/admin, service role | stores or replaces a key in Vault |
| `delete_tenant_secret(tenant, name)` | owner/admin, service role | removes it from the table and Vault |
| `get_tenant_secret(tenant, name)` | **service role only** | returns the decrypted value |
| `match_chunks(tenant, embedding, count, min_similarity)` | signed-in user, service role | semantic search; security invoker, so RLS still applies |

The Supabase security advisor warns that signed-in users can call the four `SECURITY DEFINER`
functions above. That is intended: each one checks the caller's membership and role itself
(see the isolation test).

### Decisions to revisit

- **Embedding size is 1536** (e.g. OpenAI `text-embedding-3-small`). The model is stored per
  chunk. Changing the dimension needs a migration and a re-embed.
- **`records.fts` uses the `simple` text configuration**, which does not split Chinese into
  words. Chinese search relies on the trigram index on `title` and on embeddings for now.
- **Deleting a user who is the last owner of a tenant is blocked** until ownership is
  transferred or the tenant is deleted.

## Applying migrations

New migrations go in `supabase/migrations/` as `YYYYMMDDHHMMSS_name.sql`. They are applied
either with the Supabase CLI (`supabase link --project-ref xhaqzwznduxoosqtcrrm`, then
`supabase db push`) or by pasting them into the SQL Editor. When the SQL Editor is used,
record the file in the migration history so the CLI stays in step:

```sql
insert into supabase_migrations.schema_migrations (version, name)
values ('20261015000500', 'advisor_fixes');
```

(From a Claude Code cloud session, the Supabase MCP `apply_migration` tool and very large SQL
statements timed out on 2026-10-15; small statements through `execute_sql` worked. Paste big
files into the SQL Editor instead.)

## Running the isolation test

Paste `supabase/tests/isolation_test.sql` into the SQL Editor and run it. It creates four test
users and two tenants, checks 27 rules as each role, then rolls everything back. The result is
always shown as an error:

- `ERROR: ALL CHECKS PASSED (27 checks)` — good
- `ERROR: FAIL: <what went wrong>` — a rule is broken; nothing was saved either way

Run it again after every migration that touches tables, policies or functions.
