# portal/ — Genie sign-up and workspace admin (BAS 2.0 step 2)

Next.js 16 (App Router) + Supabase Auth. Uses the shared schema in `../shared/` through the
signed-in user's session, so row-level security decides what every page can see and change.

> This Next.js version has breaking changes from older releases (e.g. `proxy.ts` replaces
> `middleware.ts`; `params`, `searchParams` and `cookies()` are async). Check
> `node_modules/next/dist/docs/` before changing framework code.

## What it does

| Page | Who | What |
|---|---|---|
| `/` | anyone | Landing page; signed-in users go straight to `/app` |
| `/login` | anyone | Continue with Google or Microsoft (each shown only when enabled in Supabase), or email + password: sign in / create account / forgot password |
| `/reset-password` | signed in | Choose a new password. The reset email signs the user in through `/auth/confirm` and lands here |
| `/auth/confirm` | — | Return page for Google sign-in and email-confirmation links: reads the session from the URL fragment (implicit flow), stores it in this browser's cookies, wipes it from the address bar |
| `/auth/callback` | — | Server-side finish for PKCE `code` or `token_hash` links (kept for OAuth and future custom email templates) |
| `/app` | signed in | Your workspaces; with none, goes to `/app/new` |
| `/app/new` | signed in | Create a workspace (`create_tenant`); you become its owner |
| `/app/[slug]` | members | Redirects to Ask — the workspace's home (Overview page removed 2026-10-16) |
| `/app/[slug]/help` | members | Help centre: searchable articles by topic (`lib/help.ts`) |
| `/app/[slug]/ask` | members | Home, Copilot-style: greeting, large message box (Enter sends, Shift+Enter new line), suggestion cards that fit the switched-on sources; then a centred thread with the box at the bottom and "New chat". Owners/admins also see a closable setup strip |
| `/app/[slug]/members` | members | Member list; owners/admins invite by link, change roles, remove people |
| `/app/[slug]/settings` | owners/admins | One page for workspace configuration: **Data sources** (Odoo on/off, read live), **AI model keys** (bring-your-own, Supabase Vault), **AI agent access (MCP)** (create/revoke API keys, Claude Desktop config). `/sources`, `/keys` and `/agents` redirect to its sections |
| `/api/mcp` | API key | Genie MCP server (see below) |
| `/invite/[token]` | signed in | Accept an invitation (`accept_invitation`); must be signed in with the invited email |
| `/privacy`, `/terms` | anyone | Privacy Policy and Terms of Service (drafts; company details in `lib/legal.ts`, to be confirmed and legally reviewed) |

The product name lives only in `lib/brand.ts`.

**Look and feel: ERPNext / Frappe desk** (user request 2026-10-16). Tokens in `app/globals.css` (white page,
near-black ink `#1f272e`, grey `#f3f3f3` fills, black primary buttons, colour only for status), Inter font,
16px base (enlarged 2026-10-16). **Workspace layout** (`components/workspace-shell.tsx`): top bar with logo, breadcrumbs (workspace
switcher › page), a "Search or ask Genie" box (opens Ask with the question filled in) and the account menu;
plain left sidebar (pages from `lib/nav.ts`, data-source status, closable "what's new" note from
`lib/whats-new.ts`); page head with a sidebar toggle and the title. Phones get the sidebar as a drawer.
`/app` and `/app/new` keep the simple top bar (`app/app/(home)/layout.tsx`).

**Sign-in runs in the browser** (`app/login/auth-panel.tsx`, `lib/supabase/browser.ts`) with
Supabase's implicit flow. Email sign-in links are no longer used. The PKCE flow failed on
genie.infiniduo.com with `AuthPKCECodeVerifierMissingError`: the code-verifier cookie set when
sign-in started never came back on the callback. The implicit flow needs no such cookie.
`lib/auth-settings.ts` asks Supabase which providers are on, so the Google and Microsoft buttons only
appear once each is enabled. **Forgot password** emails a reset link (`resetPasswordForEmail`) back to
`/auth/confirm?next=/reset-password`. Until custom SMTP is set up, Supabase only delivers it to members
of the Supabase organisation.

**Sessions** are Supabase cookies managed by `@supabase/ssr`, and `proxy.ts` refreshes them
on every request. This replaces the token the legacy dashboard kept in browser storage.

**Invitations** are links shown to the inviter to copy and send. Emailing them automatically
comes later, together with a custom SMTP sender (see below).

## MCP server (`/api/mcp`)

`https://genie.infiniduo.com/api/mcp` — MCP Streamable HTTP, stateless, JSON responses
(`app/api/mcp/route.ts`, tools in `lib/mcp/server.ts`). Authenticate with a workspace API key:
`Authorization: Bearer gnk_…` (also `x-api-key`, or `?key=` for clients that cannot send headers).

| Tool | Database function | What it does |
|---|---|---|
| `workspace_info` | `mcp_workspace` | workspace name, sources, record types and counts |
| `search_records` | `mcp_search_records` | keyword search over records, optional type filter |
| `get_record` | `mcp_get_record` | all fields of one record |
| `find_contact` | `mcp_find_contact` | people/companies by name, email or phone digits |
| `search_knowledge` | `mcp_search_knowledge` | passages from policies and documents |

All tools are read-only. With Odoo on, the server turns the API key into its workspace
(`mcp_key_tenant`, service role), reads Odoo live with the workspace's key from Vault and stores
nothing. Without Odoo it calls the `mcp_*` database functions with the public key over the demo
data. Each call is metered as a `tool_call` usage event.

Claude Desktop (`claude_desktop_config.json`), via `mcp-remote`:

```json
{ "mcpServers": { "genie": { "command": "npx",
  "args": ["-y", "mcp-remote", "https://genie.infiniduo.com/api/mcp", "--header", "Authorization:Bearer ${GENIE_KEY}"],
  "env": { "GENIE_KEY": "gnk_…" } } } }
```

## Agent and model gateway (`lib/ai`)

The Ask page sends the conversation to a server action (`app/app/[slug]/ask/actions.ts`) which runs
`askAgent` (`lib/ai/agent.ts`):

- **Gateway** (`lib/ai/gateway.ts`): the workspace's own key from Vault (Anthropic → OpenRouter → xAI),
  else the platform key (`OPENROUTER_API_KEY` only — there is no platform Anthropic key). Claude goes through the
  Anthropic SDK with adaptive thinking, effort `medium` and server-side `fallbacks: "default"`
  (beta `server-side-fallback-2026-07-01`: a declined request is retried on Anthropic's recommended
  fallback model). OpenRouter and xAI use their OpenAI-compatible chat completions API.
  Models: `GENIE_ANTHROPIC_MODEL` (default `claude-opus-5-5`), `GENIE_XAI_MODEL`. OpenRouter gets a fallback list
  (`models`): `GENIE_OPENROUTER_MODEL` if set, then Qwen 3.8 Max, DeepSeek V4 Pro, GLM 5.3 — the platform account is
  in Hong Kong, where Anthropic/OpenAI/Google refuse service — and `provider.data_collection: "deny"`.
- **Speed**: the prompt names the switched-on sources and only tools that can work are offered (no
  `workspace_info` step); lookups in one step run in parallel; OpenRouter gets `reasoning.effort: low`. Each
  question logs `ask … total=…ms [model …ms tools …ms]` per step (Vercel runtime logs).
- **Model choice per workspace**: Settings → AI model keys → "Model for Ask" (`lib/ai/models.ts`), stored in
  `tenants.settings.ai_models` per route (anthropic / openrouter / xai); applies to the workspace's own key or the
  platform key. On OpenRouter the choice goes first, then `GENIE_OPENROUTER_MODEL`, then the Hong Kong-safe list.
- **Tools** (`lib/ai/tools.ts`): the same five read tools as the MCP server, executed with
  `agent_tool()` as the signed-in user, so membership is checked by the database.
- **Metering**: one `message`, plus `input_token` / `output_token` rows with `key_source`
  (`platform` or `byok`), written with the service role (`lib/supabase/admin.ts`).
- Server-only env vars: `SUPABASE_SECRET_KEY`, `OPENROUTER_API_KEY` — mark them
  Sensitive in Vercel, never `NEXT_PUBLIC_`.

## Saved keys: show and copy (`components/secret-input.tsx`, `app/app/[slug]/reveal-action.ts`)

Every key field (Odoo API key, search query key, Slack token and signing secret) shows a saved key as dots with
👁 show and ⧉ copy; saved AI keys have the same icons in their list. The value is fetched from Vault only on
click, by `revealSecret` (owners/admins, key must belong to the workspace). Typing replaces the key; untouched
dots keep it. Workspace API keys for agents (`gnk_…`) can't be shown — only their hash is kept. (Decided
2026-10-16 at the user's request; previously keys could never be read back. Privacy policy updated.)

## Slack (`lib/slack`, `app/api/slack/[slug]/events`)

Settings → **Channels** → Slack: a workspace connects **its own Slack app** (new, or an existing bot such as C21's
`c21_property_chatbot` in Slack workspace C21net). Bot token + signing secret go to Vault (`slack_bot_token`,
`slack_signing_secret`, kind `other`); the Slack workspace and bot name to `tenants.settings.channels.slack`.
In the Slack app: Event Subscriptions → Request URL `https://genie.infiniduo.com/api/slack/<slug>/events`, bot
events `app_mention` + `message.im`; scopes `app_mentions:read`, `chat:write`, `im:history`, `channels:history`.
The endpoint checks Slack's signature, acknowledges at once and answers in `after()`: "⏳ Looking it up…" is
posted, then replaced by the answer (Markdown → Slack mrkdwn). Thread history is read back from Slack for
context; nothing is stored. Runs the same agent as Ask with `channel = "slack"` and no signed-in user, so
only switched-on live sources answer. Anyone who can message the bot in that Slack workspace can ask.
**On/off:** the Slack switch sets `settings.channels.slack.enabled`; off = the endpoint acknowledges and ignores
events (keys kept). "Disconnect" deletes the keys.

## Data sources (`lib/odoo`) — read live, nothing stored

**Decided 2026-10-16: Genie keeps no copy of customer business data.** Tools read the customer's
system at question time; Genie stores only the connection (address, settings) and the API key (Vault).

**Odoo** (`lib/odoo/client.ts`, `lib/odoo/live.ts`, `lib/odoo/source.ts`), read-only:
- Settings → Data sources shows an on/off card. Turning it on asks for the address and API key
  (database name only for self-hosted Odoo; login email only for Odoo 18 or older), checks them with
  Odoo, and saves the source (`status = active`) and the key in Vault. Turning it off deletes both.
  No picking what to read: at switch-on Genie checks which of contacts (`res.partner`), CRM leads
  (`crm.lead`) and listings (`x_c21_listing`) the Odoo user can read (`search_count`), plus any models typed
  under "Other Odoo data", and reads those. Access is limited through the Odoo user's own permissions.
- The client tries the JSON-2 API (`/json/2/<model>/<method>`, Odoo 19+) and falls back to the
  legacy JSON-RPC endpoint (`/jsonrpc`, `execute_kw`).
- Tools (`runLiveTool`): `workspace_info` (types + live counts), `search_records` (every word must
  match one of up to 8 text fields, `ilike`, newest first), `get_record` (id `<model>:<odoo id>`, all
  readable stored fields, many2one → name, selection → label, HTML → text, plus a link to Odoo),
  `find_contact` (`res.partner` by name/email/phone, phone also on the last 8 digits),
  `search_knowledge` (empty until a document source exists). Field lists are cached 10 minutes.
- Used by Ask (`lib/ai/agent.ts`) and the MCP server (`lib/mcp/server.ts`) whenever the workspace has
  Odoo on; each call is metered as `tool_call`. Workspaces without Odoo (the demo tenant) still use
  the database tools over `records`.
- Not yet: SQL databases (live, read-only).

**Azure AI Search index** (`lib/search/azure.ts`, kind `azure_search`), read-only: the customer's own
index, searched live with a **query key** (can only search). Settings card asks for service address,
index, query key, and (advanced) semantic configuration + vector field. `search_knowledge` uses it:
keyword + semantic reranker + captions; a `text` vector query is added when the index has a vectorizer
(falls back by itself when it has none). `get_record` with `search:<doc key>` returns one document.
`lib/live.ts` combines the switched-on sources for Ask and the MCP server.

C21: service `c21net-bas-srch-ea-prod` (C21's Azure, RG `c21net-bas-app-ea-prod-etl`), index
`properties-index` (~5,700 docs: SharePoint building folders, proposals, listings, photo captions; built
by `legacy/` jobs), query key `genie-readonly` (created 2026-10-16). No vectorizer on the index yet, so
search is keyword + semantic; adding an Azure OpenAI vectorizer (`text-embedding-3-large`, 3072 dims) to
the index turns on vector search with no Genie change.

## Run locally

```bash
cd portal
cp .env.example .env.local    # fill in the publishable key
npm install
npm run dev                   # http://localhost:3000
```

Checks before pushing: `npx tsc --noEmit`, `npm run lint`, `npm run build`.

## Supabase settings this needs

In the Supabase dashboard for project `genie` → **Authentication → URL Configuration**:

- **Site URL**: `https://genie.infiniduo.com`
- **Redirect URLs**: `https://genie.infiniduo.com/**` and `http://localhost:3000/**`.
  Sign-in links to any other address are refused.

**Sign-in methods** (Authentication → Sign In / Providers):

- **Email**: enabled. **Confirm email** is currently **on** (2026-10-16), so new accounts must click the emailed link first;
  Supabase's built-in email is limited to a few messages an hour. Turn it back on once custom SMTP
  is set up.
- **Google**: enabled 2026-10-16 with Google Cloud project **Genie** (`genie-511800`). Its consent screen is in
  **Testing**, so only test users listed on its Audience page can sign in until it is published. OAuth client
  "Genie web (Supabase)" (Web application) whose authorised
  redirect URI is `https://xhaqzwznduxoosqtcrrm.supabase.co/auth/v1/callback`.
- **Azure (Microsoft)**: enabled 2026-10-16. App registration **Genie** in the Infinity Duo Entra tenant
  (client ID `2cb0fc03-7649-46c1-8898-9c908952dc90`), any work/school or personal Microsoft account, Web
  redirect URI `https://xhaqzwznduxoosqtcrrm.supabase.co/auth/v1/callback`. Tenant URL left empty in Supabase.
  **The client secret "Supabase sign-in" expires 2028-10-15**: before then, add a new secret in Entra
  (Certificates & secrets) and paste its Value into Supabase.

**Email sending:** Supabase's built-in email service only delivers to members of the Supabase
organisation and allows a few emails per hour. That is enough to test with your own address.
Before real users sign up, set up custom SMTP (e.g. Resend) under **Authentication → Emails → SMTP Settings**.

## Deploy (Vercel)

Served at **https://genie.infiniduo.com** by the Vercel project `nextjs-dashboard`
(team Infinity Duo Technology), which used to serve the legacy dashboard. Settings:

- Git repository `lojul/bas2`, production branch `main`
- **Root Directory = `portal`**, framework preset Next.js, no build/output overrides
- **Functions run in Singapore (`sin1`, `portal/vercel.json`)**, next to Supabase. Not Hong Kong:
  Anthropic does not serve Hong Kong, and OpenRouter refused Claude requests from `hkg1` with
  "prohibited due to a violation of provider Terms Of Service" (2026-10-16).
- Environment variables: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`,
  `NEXT_PUBLIC_SITE_URL=https://genie.infiniduo.com` (production)

Every merge to `main` that touches `portal/` deploys to production.
