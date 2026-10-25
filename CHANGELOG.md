# Change log

What changed in Genie (genie.infiniduo.com) and its set-up, newest first. One line per change, with the pull
request (`#n`) where there is one. Add a line whenever a change ships or a workspace's set-up changes.

## 2026-10-25

- Docs: Infinity Duo's WhatsApp set-up; working notes for applying migrations through Chrome (#86)

## 2026-10-24

- **WhatsApp can change Odoo**: Genie replies with a draft; reply YES to save, NO to cancel (#85)
- **WhatsApp remembers the last 30 minutes** (`whatsapp_turns`, deleted automatically). New data exception, user decision; privacy policy updated (#85)
- Set-up: migration `20261024000100_whatsapp_changes` applied to `genie`
- Set-up: Infinity Duo's Twilio SID and Auth Token saved in Genie, WhatsApp switched on (Sandbox +1 415 523 8886)

## 2026-10-21

- WhatsApp answers only members' linked numbers (Team → Link WhatsApp → send "LINK <code>") (#83)
- Odoo can be connected with an MCP-scoped key for reading (#81); Changes in Odoo work with a separate RPC key (#82)
- Set-up: Infinity Duo workspace (`infiniduo`) with its own Odoo 20 and its own Twilio Sandbox (#84)
- Docs: Genie design docs with diagrams; slimmer CLAUDE.md (#79, #80)

## 2026-10-19

- Ask: Download PDF under answers to a PDF request, rendered on the server with Chinese fonts; staff-only notes and confidential files left out (#71–#78)
- Ask: a new chat switches to the conversation at once (#70)

## 2026-10-18

- Sidebar: delete a chat (confirm dialog) (#66–#69)
- Ask: fix new chat stuck on "Starting the chat…" (#65)

## 2026-10-17

- **Ask: changes in Odoo** (draft → Confirm), per-action controls and an Activity log (#59)
- **Ask: saved team and private chats** (@Genie in team chats), kept 90 days (#53, #54)
- **Genie on WhatsApp** (Twilio Sandbox): text answered, photos/files to the document intake (#43, #44)
- Team: invite link with email + password, invitation history (#45, #55)
- Navigation, top bar and sidebar simplified; larger text (#47–#52, #58, #61)
- Settings: key fields masked with show/copy; forms open by default; faster tabs (#38–#41)
- Sign-in: Google and Microsoft marked "Coming soon" (#46)
- Ask: commercial sample questions; shorter hints (#60, #64)
- Docs: concept and technical overview, WhatsApp research, status (#42, #56, #57, #62, #63)

## 2026-10-16

- **Genie reads Odoo live** — no copy of customer data (#19)
- **Search C21's document index live** (Azure AI Search) (#20)
- **Genie in Slack**, with an on/off switch (#35–#37)
- Ask: home page, Copilot-style, faster and formatted answers, model choice per workspace (#24, #29, #33, #34)
- Settings: data sources edited in place, Test connection, Save, switch top right (#25–#28, #30, #31)
- ERPNext-style look; sidebar and Help centre (#13, #23)
- Password reset; Microsoft sign-in (#11, #14)
- Platform AI key is OpenRouter only; models that serve Hong Kong (#10, #22)
- Fixes: Ask usage metering (#32); functions run in Singapore (#21); Odoo form keeps values, hides database for Odoo Online (#15, #17, #18)
- Docs: Google sign-in details, next steps and merge flow (#12, #16)

## 2026-10-15

- Supabase project `genie`: tenants, row-level security, Vault, metering (#1)
- Genie portal live at genie.infiniduo.com: sign-in, workspaces, members, AI keys (#2, #4–#6)
- Privacy Policy and Terms of Service (#3)
- Genie MCP server, Ask agent and model gateway (#7)
- Connect Odoo as a data source; one Settings tab for sources, keys and MCP (#8, #9)
