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
| `/login` | anyone | Email sign-in link (no password). The same link creates the account |
| `/auth/callback` | — | Finishes sign-in from the emailed link (PKCE `code` or `token_hash`) |
| `/app` | signed in | Your workspaces; with none, goes to `/app/new` |
| `/app/new` | signed in | Create a workspace (`create_tenant`); you become its owner |
| `/app/[slug]` | members | Overview: counts and a getting-started checklist |
| `/app/[slug]/members` | members | Member list; owners/admins invite by link, change roles, remove people |
| `/app/[slug]/keys` | owners/admins | Bring-your-own AI keys (Anthropic, OpenRouter, xAI, Azure OpenAI), stored in Supabase Vault |
| `/invite/[token]` | signed in | Accept an invitation (`accept_invitation`); must be signed in with the invited email |

The product name lives only in `lib/brand.ts`.

**Sessions** are Supabase cookies managed by `@supabase/ssr`, and `proxy.ts` refreshes them
on every request. This replaces the token the legacy dashboard kept in browser storage.

**Invitations** are links shown to the inviter to copy and send. Emailing them automatically
comes later, together with a custom SMTP sender (see below).

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
