// Workspace sidebar items and the page heading each one shows. Safe for client components.
export type NavKey = "ask" | "members" | "settings" | "help";

export type NavItem = {
  key: NavKey;
  path: string; // relative to /app/<slug>
  label: string;
  title: string;
  subtitle: string;
  managersOnly?: boolean;
  bare?: boolean; // no big page title (Ask has its own greeting)
};

export const NAV: NavItem[] = [
  // Ask is the workspace's home page (/app/<slug> redirects here; the Overview page was removed 2026-10-16).
  {
    key: "ask",
    path: "/ask",
    label: "Ask",
    title: "Ask",
    subtitle: "Ask about your company's data in plain language. Answers come only from your own systems; the conversation is not saved.",
    bare: true,
  },
  { key: "members", path: "/members", label: "Team", title: "Team", subtitle: "Who can use this workspace, and what they can change." },
  {
    key: "settings",
    path: "/settings",
    label: "Settings",
    title: "Settings",
    subtitle: "Data sources, AI model keys, AI agent access and channels.",
    managersOnly: true,
  },
  { key: "help", path: "/help", label: "Help", title: "Help", subtitle: "How to set up and use Genie, and what it can't do yet." },
];

// The nav item for a pathname such as /app/acme/settings (sub-pages like /sources count as settings).
export function activeNav(pathname: string, slug: string): NavItem {
  const rest = pathname.slice(`/app/${slug}`.length);
  if (/^\/(sources|keys|agents)(\/|$)/.test(rest)) return NAV.find((n) => n.key === "settings")!;
  return NAV.find((n) => n.path && (rest === n.path || rest.startsWith(`${n.path}/`))) ?? NAV[0];
}
