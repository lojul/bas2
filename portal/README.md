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
| `/login` | anyone | Continue with Google (shown only when enabled in Supabase), or email + password: sign in / create account |
| `/auth/confirm` | — | Return page for Google sign-in and email-confirmation links: reads the session from the URL fragment (implicit flow), stores it in this browser's cookies, wipes it from the address bar |
| `/auth/callback` | — | Server-side finish for PKCE `code` or `token_hash` links (kept for OAuth and future custom email templates) |
| `/app` | signed in | Your workspaces; with none, goes to `/app/new` |
| `/app/new` | signed in | Create a workspace (`create_tenant`); you become its owner |
| `/app/[slug]` | members | Overview: counts and a getting-started checklist |
| `/app/[slug]/members` | members | Member list; owners/admins invite by link, change roles, remove people |
| `/app/[slug]/keys` | owners/admins | Bring-your-own AI keys (Anthropic, OpenRouter, xAI, Azure OpenAI), stored in Supabase Vault |
| `/app/[slug]/agents` | owners/admins | Create and revoke API keys for AI agents; shows the MCP endpoint and a Claude Desktop config |
| `/api/mcp` | API key | Genie MCP server (see below) |
| `/invite/[token]` | signed in | Accept an invitation (`accept_invitation`); must be signed in with the invited email |
| `/privacy`, `/terms` | anyone | Privacy Policy and Terms of Service (drafts; company details in `lib/legal.ts`, to be confirmed and legally reviewed) |

The product name lives only in `lib/brand.ts`.

**Sign-in runs in the browser** (`app/login/auth-panel.tsx`, `lib/supabase/browser.ts`) with
Supabase's implicit flow. Email sign-in links are no longer used. The PKCE flow failed on
genie.infiniduo.com with `AuthPKCECodeVerifierMissingError`: the code-verifier cookie set when
sign-in started never came back on the callback. The implicit flow needs no such cookie.
`lib/auth-settings.ts` asks Supabase which providers are on, so the Google button only appears
once Google is enabled. Password reset is not built yet (needs custom SMTP); the page points to the
support address meanwhile.

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

All tools are read-only. The server holds no database secret: it calls the `mcp_*` functions with
the public key, and the database checks the API key and limits every query to that workspace.
Each call is metered as a `tool_call` usage event.

Claude Desktop (`claude_desktop_config.json`), via `mcp-remote`:

```json
{ "mcpServers": { "genie": { "command": "npx",
  "args": ["-y", "mcp-remote", "https://genie.infiniduo.com/api/mcp", "--header", "Authorization:Bearer ${GENIE_KEY}"],
  "env": { "GENIE_KEY": "gnk_…" } } } }
```

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

- **Email**: enabled. **Confirm email** is off for now, so new accounts can sign in immediately;
  Supabase's built-in email is limited to a few messages an hour. Turn it back on once custom SMTP
  is set up.
- **Google**: enabled with a Google Cloud OAuth client (Web application) whose authorised
  redirect URI is `https://xhaqzwznduxoosqtcrrm.supabase.co/auth/v1/callback`.

**Email sending:** Supabase's built-in email service only delivers to members of the Supabase
organisation and allows a few emails per hour. That is enough to test with your own address.
Before real users sign up, set up custom SMTP (e.g. Resend) under **Authentication → Emails → SMTP Settings**.

## Deploy (Vercel)

Served at **https://genie.infiniduo.com** by the Vercel project `nextjs-dashboard`
(team Infinity Duo Technology), which used to serve the legacy dashboard. Settings:

- Git repository `lojul/bas2`, production branch `main`
- **Root Directory = `portal`**, framework preset Next.js, no build/output overrides
- Environment variables: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`,
  `NEXT_PUBLIC_SITE_URL=https://genie.infiniduo.com` (production)

Every merge to `main` that touches `portal/` deploys to production.
