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
          "1. Connect a data source: Settings → Data sources → Connect Odoo, then press Sync now.",
          "2. Invite your colleagues: Team → Invite someone, then send them the link.",
          "3. Ask your first question on the Ask page, for example \"Which leads came in this week?\"",
          "4. Optional: add your own AI key, or give an outside AI agent (such as Claude Desktop) access under Settings → AI agent access.",
        ],
        link: { label: "Open Settings", path: "/settings#data-sources" },
      },
      {
        id: "what",
        title: "What Genie does",
        summary: "An AI layer over your own business data.",
        body: [
          "Genie copies records from your business systems (Odoo today) into one searchable store for your workspace, then lets your team ask questions about them in plain language.",
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
          "Sync runs when you press Sync now; scheduled sync is not available yet. Records deleted in Odoo stay in Genie until the source is removed.",
          "Each sync copies up to 5,000 rows per Odoo model; later syncs copy only rows that changed.",
          "Genie can read and search, but cannot yet create leads or records, or search the web.",
          "Conversations on the Ask page are not saved.",
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
          "4. Tick what to copy — Contacts, CRM leads (and Listings for C21) — press Connect, then Sync now.",
          "The key is kept in an encrypted vault and is never shown again. Only owners and admins can connect sources.",
        ],
        link: { label: "Connect Odoo", path: "/settings#data-sources" },
      },
      {
        id: "sync",
        title: "What gets copied, and when",
        summary: "Text, numbers, dates and choices — on demand.",
        body: [
          "Genie copies stored fields: text, numbers, dates, choices (shown by their label) and links to other records (shown by name). Formatted text is turned into plain text.",
          "The first sync copies up to 5,000 rows per model. After that, each sync copies only rows changed in Odoo since the last sync.",
          "If a sync fails, the reason is shown under Settings → Data sources, and the dot next to the source in the sidebar turns red.",
        ],
      },
      {
        id: "other-sources",
        title: "SQL databases and spreadsheets",
        summary: "Coming soon.",
        body: [
          "Connecting a SQL database (read-only) and uploading CSV or spreadsheet files are the next data sources we are building. Odoo is not required: a workspace can run on SQL or spreadsheets alone.",
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
        link: { label: "Add a key", path: "/settings#ai-keys" },
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
        link: { label: "Create a key", path: "/settings#ai-agents" },
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
          "The person must sign in with that same email address to accept. The link works once and expires after 7 days.",
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
        summary: "Your workspace's copied records — separated from every other workspace.",
        body: [
          "Each workspace's data is kept apart from every other workspace by the database itself. Keys (Odoo, AI) are kept in an encrypted vault.",
          "Data is hosted in Singapore. Questions you ask are sent to the AI provider that answers them.",
        ],
        link: { label: "Privacy Policy", path: "/privacy", abs: true },
      },
      {
        id: "signin",
        title: "Sign in with Google, Microsoft or email",
        summary: "Use whichever account your company uses.",
        body: [
          "Use Continue with Google, Continue with Microsoft (work, school or personal account), or an email address and password.",
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
