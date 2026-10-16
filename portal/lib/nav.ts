// Workspace sidebar items and the page heading each one shows. Safe for client components.
export type NavKey = "overview" | "ask" | "members" | "settings" | "help";

export type NavItem = {
  key: NavKey;
  path: string; // relative to /app/<slug>
  label: string;
  title: string;
  subtitle: string;
  managersOnly?: boolean;
};

export const NAV: NavItem[] = [
  { key: "overview", path: "", label: "Overview", title: "Overview", subtitle: "Your workspace at a glance and what to set up next." },
  { key: "ask", path: "/ask", label: "Ask", title: "Ask", subtitle: "Ask questions about your company's data in plain language." },
  { key: "members", path: "/members", label: "Team", title: "Team", subtitle: "Who can use this workspace, and what they can change." },
  {
    key: "settings",
    path: "/settings",
    label: "Settings",
    title: "Settings",
    subtitle: "Data sources, AI model keys and AI agent access.",
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
