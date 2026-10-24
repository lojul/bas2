// Help articles shown on /app/<slug>/help. Plain language; keep them true to what the portal does today.
// `link.path` is relative to /app/<slug> unless it starts with "/" and "abs" is set.
export type HelpArticle = {
  id: string;
  title: string;
  summary: string;
  body: string[]; // paragraphs; a line starting with "1." etc. is shown as a numbered step
  link?: { label: string; path: string; abs?: boolean };
};

export type HelpTopic = {
  id: string;
  title: string;
  icon: "start" | "data" | "ask" | "agents" | "team" | "account";
  articles: HelpArticle[];
};

export const HELP_TOPICS: HelpTopic[] = [
  {
    id: "start",
    title: "Getting started",
    icon: "start",
    articles: [
      {
        id: "setup",
        title: "Set up Genie in 4 steps",
        summary: "From an empty workspace to your first answer.",
        body: [
          "1. Turn on a data source: Settings → Data sources → switch Odoo on (top right of the box), enter its address and API key, and press Save.",
          "2. Invite your colleagues: Team → Invite someone, then send them the link.",
          "3. Ask your first question on the Ask page, for example \"Which leads came in this week?\"",
          "4. Optional: add your own AI key, or give an outside AI agent (such as Claude Desktop) access under Settings → AI agent access.",
        ],
        link: { label: "Open Settings", path: "/settings?tab=data-sources" },
      },
      {
        id: "what",
        title: "What Genie does",
        summary: "An AI layer over your own business data.",
        body: [
          "Genie lets your team ask questions about your business systems (Odoo today) in plain language. It reads the system live at the moment a question is asked and keeps no copy of your records.",
          "Your own system stays the system of record. Genie only reads from it; it does not change anything in Odoo.",
          "The same data is available to outside AI agents, such as Claude or ChatGPT, through Genie's MCP server — only with an API key you create.",
        ],
      },
      {
        id: "limits",
        title: "Beta limits and what isn't supported yet",
        summary: "What to expect while Genie is in beta.",
        body: [
          "Data sources: Odoo only. SQL databases and CSV/spreadsheet upload are coming next.",
          "Search is keyword search inside Odoo: every word you type must appear in the record (name, address, notes …). Differently worded questions may miss.",
          "Answers are as fast as your Odoo: usually a few seconds per question.",
          "Genie can read and search, but cannot yet create leads or records, or search the web.",
          "Chats on Ask are kept for 90 days after their last message, then deleted automatically.",
          "Slack, WhatsApp and Teams are on the way.",
        ],
      },
    ],
  },
  {
    id: "data",
    title: "Connect your data",
    icon: "data",
    articles: [
      {
        id: "odoo",
        title: "Connect Odoo",
        summary: "Read-only, with an API key for a dedicated Odoo user.",
        body: [
          "1. In Odoo, create (or pick) a user that can read the data you want in Genie — ideally one used only for integrations.",
          "2. Signed in as that user: Preferences → Account Security → New API Key. Copy the key.",
          "3. In Genie: Settings → Data sources → Connect Odoo. Enter your Odoo address and the API key. If you run your own Odoo server (not yourcompany.odoo.com), Genie also asks for the database name. For Odoo 18 or older, open \"Using Odoo 18 or older?\" and enter that user's login email.",
          "4. Press Save. Genie reads the contacts, CRM leads and listings that this Odoo user may see — nothing to pick.",
          "The key is kept in an encrypted vault and is never shown again. Only owners and admins can connect sources.",
        ],
        link: { label: "Connect Odoo", path: "/settings?tab=data-sources" },
      },
      {
        id: "live",
        title: "Read live — nothing is copied",
        summary: "Text, numbers, dates and choices — on demand.",
        body: [
          "When someone asks a question, Genie looks it up in Odoo at that moment, with the API key you gave it, and shows the result. Nothing is saved in Genie, so answers are always current.",
          "Genie stores only the connection: the Odoo address and the API key (encrypted). Turning Odoo off deletes both.",
          "Genie reads only what the Odoo user behind the key may see. To limit it, limit that user's access in Odoo.",
        ],
      },
      {
        id: "search-index",
        title: "Search your documents (Azure AI Search)",
        summary: "Use your own search index — read live with a read-only key.",
        body: [
          "If your documents are already indexed in Azure AI Search (for example SharePoint folders), Genie can search that index directly: Settings → Data sources → switch Document search index on.",
          "Enter the search service address, the index name and a query key (Azure portal → search service → Keys → Manage query keys). A query key can only search; it cannot change anything.",
          "Results are ranked by meaning when the index has a semantic configuration, and link back to the original file. Nothing is copied into Genie.",
        ],
        link: { label: "Open Data sources", path: "/settings?tab=data-sources" },
      },
      {
        id: "other-sources",
        title: "SQL databases",
        summary: "Coming soon.",
        body: [
          "Reading a SQL database live (read-only) is the next data source we are building. Odoo is not required: a workspace can run on a SQL database alone.",
        ],
      },
    ],
  },
  {
    id: "ask",
    title: "Ask and AI models",
    icon: "ask",
    articles: [
      {
        id: "odoo-changes",
        title: "Changes in Odoo (create leads, notes, follow-ups)",
        summary: "Genie prepares the change; you press Confirm.",
        body: [
          "An owner or admin switches it on in Settings → Data sources → Changes in Odoo, pastes the API key of a dedicated \"Genie\" Odoo user, and ticks what Genie may prepare: create a lead, create a contact, add a note, schedule a follow-up, update allowed fields. For each, choose who may ask (members and admins, or admins only). Viewers never can.",
          "On Ask, write for example: \"Create a lead for Chan Tai Man, 9123 4567, wants a 3-bed in Taikoo Shing\". Genie shows a draft card. Nothing is saved in Odoo until you press Confirm; Cancel throws it away; a draft expires after 24 hours.",
          "Only the person who asked, or an owner/admin, can confirm. The Odoo record gets a note \"Done by Genie at the request of …\", and the change is listed in Settings → Activity.",
          "On WhatsApp (from a linked number) it works the same way: Genie replies with the draft — reply YES to save it in Odoo or NO to cancel. YES or NO applies to the drafts in Genie's latest reply. On Slack Genie still only reads.",
        ],
      },
      {
        id: "team-chats",
        title: "Team chats and private chats",
        summary: "Talk with colleagues and Genie in one place.",
        body: [
          "On Ask, choose Private (only you; Genie answers every message) or Team (everyone in the workspace, including people who join later).",
          "In a team chat, people talk to each other; write @Genie in a message when you want Genie to answer. Messages appear live for everyone in the chat.",
          "Start a new chat with New chat; the chat is named after its first message. Delete a chat with Delete at the top — for everyone.",
          "Chats are deleted automatically 90 days after their last message.",
        ],
      },
      {
        id: "asking",
        title: "Ask questions about your data",
        summary: "Plain language in, answers from your own records.",
        body: [
          "Open Ask and type a question. Genie searches your workspace's records, contacts and documents and answers from what it finds.",
          "Good questions name what you want: \"Show leads from Kowloon this month\", \"Find the contact for Harbour Supplies\".",
          "Answers come only from your workspace. If the data isn't there, Genie says so instead of guessing.",
        ],
        link: { label: "Open Ask", path: "/ask" },
      },
      {
        id: "models",
        title: "Which AI model answers",
        summary: "Your own key if you added one, otherwise ours.",
        body: [
          "If your workspace has its own AI key, Genie uses it — Anthropic first, then OpenRouter, then xAI. Otherwise it uses Genie's platform key.",
          "Every question is counted (messages and tokens) for the workspace, so usage can be billed later.",
        ],
      },
      {
        id: "own-key",
        title: "Use your own AI key",
        summary: "Anthropic, OpenRouter or xAI.",
        body: [
          "Owners and admins: Settings → AI model keys → choose the provider and paste the key. It is stored in an encrypted vault and cannot be read back.",
          "Azure OpenAI keys can be saved but are not used by Ask yet.",
        ],
        link: { label: "Add a key", path: "/settings?tab=ai-keys" },
      },
    ],
  },
  {
    id: "agents",
    title: "AI agents (MCP)",
    icon: "agents",
    articles: [
      {
        id: "mcp-key",
        title: "Give an AI agent access",
        summary: "Create a workspace API key for Claude, ChatGPT or your own agent.",
        body: [
          "1. Settings → AI agent access → Create key. Copy it straight away; it is shown only once.",
          "2. Point the agent at https://genie.infiniduo.com/api/mcp and send the key as \"Authorization: Bearer <key>\".",
          "3. Revoke the key on the same page when the agent no longer needs access.",
        ],
        link: { label: "Create a key", path: "/settings?tab=ai-agents" },
      },
      {
        id: "claude-desktop",
        title: "Connect Claude Desktop",
        summary: "A ready-made config is shown when you create a key.",
        body: [
          "After you create a key, Settings → AI agent access shows a claude_desktop_config.json snippet. Paste it into Claude Desktop's config file and restart Claude.",
          "Claude can then search this workspace's records, contacts and documents on its own.",
        ],
      },
      {
        id: "tools",
        title: "What agents can do",
        summary: "Read-only tools, limited to this workspace.",
        body: [
          "workspace_info, search_records, get_record, find_contact and search_knowledge. All are read-only.",
          "A key only ever sees the workspace it was created in.",
        ],
      },
    ],
  },
  {
    id: "team",
    title: "Team",
    icon: "team",
    articles: [
      {
        id: "invite",
        title: "Invite people",
        summary: "Send an invite link; it works once, for 7 days.",
        body: [
          "Owners and admins: Team → Invite someone → enter their email and role. Copy the link and send it yourself (by email, Slack, WhatsApp …).",
          "On the link they choose a password for that email address — no confirmation email needed. The link works once and expires after 7 days.",
        ],
        link: { label: "Open Team", path: "/members" },
      },
      {
        id: "roles",
        title: "Roles explained",
        summary: "Owner, Admin, Member, Viewer.",
        body: [
          "Owner: everything, including managing other owners. A workspace always keeps at least one owner.",
          "Admin: manages members (except owners), data sources, AI keys and agent access.",
          "Member: uses Ask and reads the workspace's data.",
          "Viewer: read-only.",
        ],
      },
    ],
  },
  {
    id: "account",
    title: "Privacy, sign-in and account",
    icon: "account",
    articles: [
      {
        id: "privacy",
        title: "What Genie stores",
        summary: "Account details and encrypted keys — not your business records.",
        body: [
          "Genie stores your account, workspace and team, the connection details of your data sources and AI keys (encrypted in a vault), and usage counts for billing. It does not keep a copy of your business records.",
          "Records are read from your system when a question is asked and passed to the AI provider that writes the answer. Chats on Ask are kept for 90 days after the last message (team chats are visible to every member; private chats only to you), and can be deleted any time by the person who started them or an owner/admin. On WhatsApp, Genie keeps a member's messages and its answers for 30 minutes so it can follow the conversation, then deletes them.",
          "Genie is hosted in Singapore; each workspace is kept apart from every other by the database itself.",
        ],
        link: { label: "Privacy Policy", path: "/privacy", abs: true },
      },
      {
        id: "signin",
        title: "Sign in with email and password",
        summary: "Google and Microsoft sign-in are coming soon.",
        body: [
          "Sign in with your email address and password. Google and Microsoft sign-in are coming soon.",
          "If you were invited, sign in with the address the invite was sent to.",
        ],
      },
      {
        id: "password",
        title: "Change or reset your password",
        summary: "From the account menu, or \"Forgot your password?\" on the sign-in page.",
        body: [
          "Signed in: click your email at the bottom of the sidebar → Change password.",
          "Forgot it: on the sign-in page choose Forgot your password?, enter your email and open the link we send you.",
        ],
        link: { label: "Change password", path: "/reset-password", abs: true },
      },
    ],
  },
];
