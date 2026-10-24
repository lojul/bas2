# Genie: current status

[← Design docs](README.md) · updated 2026-10-24

Live at https://genie.infiniduo.com. What's built: [Product](1-product.md). What comes next: [Roadmap](5-roadmap.md).
Update this page when an item is tested, decided or done.

## Waiting on a person: built, not yet confirmed end to end

| Item | What's needed |
|---|---|
| Slack | Request URL `https://genie.infiniduo.com/api/slack/c21/events` set in the Slack app ("Verified"), then one @mention test |
| WhatsApp (Sandbox) | Twilio Sandbox "When a message comes in" → `https://genie.infiniduo.com/api/whatsapp/c21/inbound` (POST), then a text and a photo test |
| WhatsApp (Infinity Duo) | Sandbox on in Infinity Duo's own Twilio account (SID `ACb426…`), webhook set. Still to do: paste SID + Auth Token in Genie → Infinity Duo → Settings → Channels; phone sends `join orange-minute` to +1 415 523 8886; Members → Link WhatsApp; ask a question; then "Create a lead for TEST Chan, 9123 4567" → YES → check Odoo and Settings → Activity |
| WhatsApp (Infinity Duo real number) | User prefers a **HK mobile number**: a new HK SIM (never used on WhatsApp) registered as a Twilio WhatsApp sender ("own number"); needs the Twilio account upgraded from trial and a Meta Business Portfolio |
| WhatsApp (real number) | Decide C21's number and start Meta business verification ([research](research/whatsapp.md)) |
| Changes in Odoo | Switched on for C21 (same key pasted for reading and writing). Test on Ask in a Private chat with "TEST …" records: create lead → Confirm → note → follow-up; check Settings → Activity; delete the TEST records in Odoo |
| Team chat | Two members in one Team chat: live updates and an @Genie answer |
| Usage metering | One answer on Ask, then check `usage_events` has `message` and token rows (fix shipped, unverified) |
| C21 trial | 3–5 agents use Ask/Slack/WhatsApp for a week; collect wrong, missing and slow answers |

## Decisions still to make

| Decision | Proposal |
|---|---|
| Answer layout | Short answer, then "From Odoo (live)" / "From documents"; Odoo wins on current facts |
| Vector search on C21's index | Add an Azure OpenAI vectorizer (`text-embedding-3-large`) to `properties-index`. Needs the user to run it or approve a managed identity; Claude may not copy the OpenAI key |
| AI agent access (MCP) | Make it an on/off card like the others |
| Google / Microsoft sign-in | When to set `SOCIAL_SIGNIN_READY` and publish the Google consent screen |
| C21's WhatsApp number | Existing Business-app number (coexistence, Meta Cloud API) or a new number (Twilio) |

## Housekeeping

- Rotate the n8n keys (root `CLAUDE.md` → Secrets).
- Upgrade Supabase to Pro before the first paying customer (free projects pause when idle).
- Archive the old `lojul/property-intelligence-dashboard` repo.
- Keep legacy `odoo-bas-sync` (fills `properties-index`) and the old Slack Azure Function (fallback) running.
- Renew the Microsoft Entra client secret before **2028-10-15**.
- Email sending (Resend): until then Supabase only emails members of the Supabase organisation, so invites, resets
  and sign-up confirmations don't reach customers.

## Recently shipped

| Date | What |
|---|---|
| 2026-10-24 | Changes in Odoo from WhatsApp (reply YES / NO); WhatsApp remembers the last 30 minutes |
| 2026-10-21 | WhatsApp answers only members' linked numbers (Members → Your WhatsApp → send "LINK <code>"); photos/files still forwarded to the document intake |
| 2026-10-21 | Odoo connected with an MCP key for reading; Changes in Odoo with a separate RPC key. Infinity Duo workspace (`infiniduo`) uses both |
| 2026-10-19 | Download PDF under answers to a PDF request, rendered on Genie's server (Chinese fonts bundled) |
| 2026-10-18 | Delete a chat from the sidebar (confirm dialog); new chat opens at once |
| 2026-10-17 | Changes in Odoo from Ask; saved team/private chats; WhatsApp on the Twilio Sandbox; invitation history |
| 2026-10-16 | Live Odoo and C21's document index; Slack; per-workspace model choice; Ask as home page |
| 2026-10-15 | Supabase project `genie`; portal live at genie.infiniduo.com |

Older detail is in git history and PR descriptions.
