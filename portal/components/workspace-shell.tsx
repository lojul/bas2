"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import {
  ArrowUpRight,
  Check,
  ChevronRight,
  CircleHelp,
  KeyRound,
  LayoutGrid,
  Lock,
  LogOut,
  Menu,
  MessagesSquare,
  Plus,
  Settings,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { BRAND } from "@/lib/brand";
import { NAV, type NavKey, activeNav } from "@/lib/nav";
import { ROLE_LABEL, type Role, canManage } from "@/lib/roles";
import { WHATS_NEW } from "@/lib/whats-new";

// Workspace layout in the style of the ERPNext / Frappe desk (user request 2026-10-16): a thin top
// bar with breadcrumbs, a command box and the account menu; a plain left sidebar; a page head with
// a toggle and the title. On phones the sidebar opens as a drawer.

const ICONS: Record<NavKey, typeof MessagesSquare> = {
  ask: MessagesSquare,
  members: Users,
  settings: Settings,
  help: CircleHelp,
};

export type ShellWorkspace = { slug: string; name: string; role: Role };
// A saved chat, listed under Ask in the sidebar.
export type SidebarChat = { id: string; title: string; visibility: "team" | "private" };

// One line in the sidebar status lists (data sources, channels).
export type StatusItem = { name: string; state: "on" | "off" | "error" };

const DISMISS_KEY = "genie.whatsNew.dismissed";

// Whether the current "what's new" note was closed in this browser. Read from localStorage after
// hydration; the server render treats it as closed so the note never flashes.
function readDismissed(): boolean {
  try {
    return localStorage.getItem(DISMISS_KEY) === WHATS_NEW.id;
  } catch {
    return false;
  }
}
const dismissListeners = new Set<() => void>();
function subscribeDismissed(listener: () => void) {
  dismissListeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    dismissListeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function WhatsNew({ slug, onNavigate }: { slug: string; onNavigate: () => void }) {
  const dismissed = useSyncExternalStore(subscribeDismissed, readDismissed, () => true);
  if (dismissed) return null;

  function close() {
    try {
      localStorage.setItem(DISMISS_KEY, WHATS_NEW.id);
    } catch {
      // Private window: it will show again next time, which is fine.
    }
    dismissListeners.forEach((l) => l());
  }

  return (
    <div className="relative rounded-lg border border-genie-border p-3 text-xs text-genie-muted">
      <button type="button" onClick={close} className="absolute right-2 top-2 rounded p-0.5 hover:bg-genie-accent" aria-label="Close">
        <X size={13} />
      </button>
      <div className="flex items-center gap-2">
        <span className="pill bg-blue-50 font-medium text-blue-700">New</span>
        <span>{WHATS_NEW.date}</span>
      </div>
      <p className="mt-2 font-medium text-genie-ink">{WHATS_NEW.title}</p>
      <p className="mt-1 leading-relaxed">{WHATS_NEW.text}</p>
      <Link href={`/app/${slug}${WHATS_NEW.path}`} onClick={onNavigate} className="mt-2 inline-flex items-center gap-1 font-medium text-genie-ink">
        Read more <ArrowUpRight size={12} />
      </Link>
    </div>
  );
}

const DOT: Record<StatusItem["state"], string> = { on: "bg-genie-green", off: "bg-gray-300", error: "bg-genie-danger" };

// A sidebar list: one line per item with its own dot (green on, grey off, red can't reach).
// Plain status lines (user 2026-10-17: no link, no hover highlight); changes are made in Settings.
function StatusList({ title, items }: { title: string; items: StatusItem[] }) {
  return (
    <div>
      <p className="mb-1.5 px-3 text-xs font-medium uppercase tracking-wide text-genie-muted">{title}</p>
      <div className="space-y-2 px-3 py-2 text-sm">
        {items.length === 0 && <span className="text-xs text-genie-muted">None switched on</span>}
        {items.map((item) => (
          <span key={item.name} className="flex items-center gap-2">
            <span className={`h-2 w-2 shrink-0 rounded-full ${DOT[item.state]}`} />
            <span className={`truncate ${item.state === "on" ? "text-genie-ink" : "text-genie-muted"}`}>{item.name}</span>
            {item.state === "error" && <span className="text-xs text-genie-danger">· can&apos;t reach</span>}
          </span>
        ))}
      </div>
    </div>
  );
}

function Sidebar({
  workspace,
  sources,
  channels,
  chats,
  onNavigate,
}: {
  workspace: ShellWorkspace;
  sources: StatusItem[];
  channels: StatusItem[];
  chats: SidebarChat[];
  onNavigate: () => void;
}) {
  const openChat = useSearchParams().get("chat");
  const pathname = usePathname();
  const active = activeNav(pathname, workspace.slug);
  const items = NAV.filter((n) => !n.managersOnly || canManage(workspace.role));
  const base = `/app/${workspace.slug}`;

  return (
    <div className="flex h-full flex-col gap-4 py-4">
      <div>
        <nav className="space-y-px">
          {items.map((item) => {
            const Icon = ICONS[item.key];
            const on = item.key === active.key;
            return (
              <Link
                key={item.key}
                href={`${base}${item.path}`}
                onClick={onNavigate}
                className={`flex items-center gap-3 rounded-md px-3 py-2.5 text-sm ${
                  on ? "bg-genie-accent font-medium text-genie-ink" : "text-genie-ink/80 hover:bg-genie-accent"
                }`}
              >
                <Icon size={18} strokeWidth={1.75} className="text-genie-muted" /> {item.label}
              </Link>
            );
          }).flatMap((link, i) =>
            // Chats sit under Ask as its sub-navigation.
            items[i].key !== "ask"
              ? [link]
              : [
                  link,
                  <div key="chats" className="ml-[1.45rem] space-y-0.5 border-l border-genie-border pl-2">
                    <Link
                      href={`${base}/ask`}
                      onClick={onNavigate}
                      className={`flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm ${
                        active.key === "ask" && !openChat ? "font-medium text-genie-ink" : "text-genie-muted hover:bg-genie-accent hover:text-genie-ink"
                      }`}
                    >
                      <Plus size={14} /> New chat
                    </Link>
                    {chats.map((c) => (
                      <Link
                        key={c.id}
                        href={`${base}/ask?chat=${c.id}`}
                        onClick={onNavigate}
                        title={c.visibility === "team" ? "Team chat" : "Private chat"}
                        className={`flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm ${
                          openChat === c.id ? "bg-genie-accent font-medium text-genie-ink" : "text-genie-ink/80 hover:bg-genie-accent"
                        }`}
                      >
                        {c.visibility === "team" ? (
                          <Users size={13} className="shrink-0 text-genie-muted" />
                        ) : (
                          <Lock size={13} className="shrink-0 text-genie-muted" />
                        )}
                        <span className="truncate">{c.title}</span>
                      </Link>
                    ))}
                  </div>,
                ],
          )}
        </nav>
      </div>

      <StatusList title="Data sources" items={sources} />
      <StatusList title="Channels" items={channels} />

      <div className="mt-auto">
        <WhatsNew slug={workspace.slug} onNavigate={onNavigate} />
      </div>
    </div>
  );
}

// The user level: who you are, your workspaces (switch / add), password, help, sign out.
// Most people have one workspace, so switching lives here rather than in the page.
export function AccountMenu({ email, slug, workspaces = [] }: { email: string; slug?: string; workspaces?: ShellWorkspace[] }) {
  return (
    <details className="relative">
      <summary
        className="flex h-9 w-9 cursor-pointer list-none items-center justify-center rounded-full bg-genie-accent text-xs font-semibold uppercase text-genie-ink"
        title={email}
      >
        {email.slice(0, 1)}
      </summary>
      <div className="absolute right-0 z-40 mt-2 w-64 rounded-lg border border-genie-border bg-white p-1 text-sm shadow-lg">
        <p className="truncate px-3 py-2 text-xs text-genie-muted">{email}</p>
        <div className="my-1 h-px bg-genie-border" />
        <p className="px-3 pb-1 pt-1.5 text-[0.7rem] font-medium uppercase tracking-wide text-genie-muted">Workspaces</p>
        {workspaces.map((w) => (
          <Link key={w.slug} href={`/app/${w.slug}`} className="flex items-center gap-2 rounded-md px-3 py-2 hover:bg-genie-accent">
            <Check size={14} className={w.slug === slug ? "text-genie-ink" : "invisible"} />
            <span className="min-w-0 flex-1 truncate">{w.name}</span>
            <span className="text-xs text-genie-muted">{ROLE_LABEL[w.role]}</span>
          </Link>
        ))}
        <Link href="/app/new" className="flex items-center gap-2 rounded-md px-3 py-2 hover:bg-genie-accent">
          <Plus size={14} /> New workspace
        </Link>
        {workspaces.length > 1 && (
          <Link href="/app?all=1" className="flex items-center gap-2 rounded-md px-3 py-2 hover:bg-genie-accent">
            <LayoutGrid size={14} /> All workspaces
          </Link>
        )}
        <div className="my-1 h-px bg-genie-border" />
        <Link href="/reset-password" className="flex items-center gap-2 rounded-md px-3 py-2 hover:bg-genie-accent">
          <KeyRound size={14} /> Change password
        </Link>
        {slug && (
          <Link href={`/app/${slug}/help`} className="flex items-center gap-2 rounded-md px-3 py-2 hover:bg-genie-accent">
            <CircleHelp size={14} /> Help
          </Link>
        )}
        <form action="/auth/signout" method="post">
          <button type="submit" className="flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-left hover:bg-genie-accent">
            <LogOut size={14} /> Sign out
          </button>
        </form>
      </div>
    </details>
  );
}


// Close any open menu (workspace switcher, account menu) on a click outside it or after navigating.
function useCloseMenus() {
  useEffect(() => {
    const close = (e: MouseEvent) => {
      document.querySelectorAll("details[open]").forEach((d) => {
        if (!d.contains(e.target as Node) || (e.target as HTMLElement).closest("a")) d.removeAttribute("open");
      });
    };
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, []);
}

// Top bar outside a workspace (the workspace list, new workspace): same look as inside.
export function HomeTopBar({ email, crumb, workspaces }: { email: string; crumb: string; workspaces: ShellWorkspace[] }) {
  useCloseMenus();
  return (
    <header className="sticky top-0 z-30 border-b border-genie-border bg-white">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-6">
        <Link href="/app?all=1" className="mr-1 flex h-7 w-7 items-center justify-center rounded-md bg-genie-green-deep text-white" aria-label={`${BRAND.name} — all workspaces`}>
          <Sparkles size={14} />
        </Link>
        <ChevronRight size={14} className="text-genie-muted" />
        <span className="text-sm text-genie-ink">{crumb}</span>
        <div className="ml-auto">
          <AccountMenu email={email} workspaces={workspaces} />
        </div>
      </div>
    </header>
  );
}

export function WorkspaceShell({
  workspace,
  workspaces,
  email,
  sources,
  channels,
  chats,
  children,
}: {
  workspace: ShellWorkspace;
  workspaces: ShellWorkspace[];
  email: string;
  sources: StatusItem[];
  channels: StatusItem[];
  chats: SidebarChat[];
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [drawer, setDrawer] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const page = activeNav(pathname, workspace.slug);
  const base = `/app/${workspace.slug}`;

  useCloseMenus();

  return (
    <div className="flex min-h-screen flex-col bg-white">
      <header className="sticky top-0 z-30 border-b border-genie-border bg-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-6">
          {/* The workspace name is the home link (Ask); on Ask it starts a fresh conversation. */}
          <Link
            href={`${base}/ask`}
            title={`Home — ${workspace.name}`}
            onClick={(e) => {
              if (pathname === `${base}/ask`) {
                e.preventDefault();
                window.location.assign(`${base}/ask`);
              }
            }}
            className="-ml-1.5 max-w-[16rem] truncate rounded-md px-1.5 py-1 text-sm font-medium text-genie-ink hover:bg-genie-accent"
          >
            {workspace.name}
          </Link>
          <div className="ml-auto flex items-center gap-3">
            <Link href={`${base}/help`} className="hidden text-sm text-genie-ink hover:underline sm:inline">
              Help
            </Link>
            <AccountMenu email={email} slug={workspace.slug} workspaces={workspaces} />
          </div>
        </div>
      </header>

      {/* Phone drawer */}
      {drawer && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button type="button" className="absolute inset-0 bg-black/30" aria-label="Close menu" onClick={() => setDrawer(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 max-w-[85vw] overflow-y-auto bg-white px-3">
            <Sidebar workspace={workspace} sources={sources} channels={channels} chats={chats} onNavigate={() => setDrawer(false)} />
          </aside>
        </div>
      )}

      <div className="mx-auto flex w-full max-w-7xl flex-1 px-6">
        {!collapsed && (
          <aside className="sticky top-16 hidden h-[calc(100vh-4rem)] w-64 shrink-0 overflow-y-auto pr-6 md:block">
            <Sidebar workspace={workspace} sources={sources} channels={channels} chats={chats} onNavigate={() => {}} />
          </aside>
        )}
        <main className={`min-w-0 flex-1 py-6 ${collapsed ? "" : "md:pl-6"}`}>
          <div className={`flex items-center gap-2 ${page.bare ? "mb-1" : "mb-5"}`}>
            <button
              type="button"
              className="rounded-md p-1 text-genie-muted hover:bg-genie-accent"
              aria-label="Toggle sidebar"
              onClick={() => (window.matchMedia("(min-width: 768px)").matches ? setCollapsed(!collapsed) : setDrawer(true))}
            >
              <Menu size={18} />
            </button>
            <div className="min-w-0">
              <h1 className={page.bare ? "sr-only" : "truncate text-xl font-semibold text-genie-ink"}>{page.title}</h1>
            </div>
          </div>
          {!page.bare && <p className="-mt-3 mb-5 pl-9 text-sm text-genie-muted">{page.subtitle}</p>}
          {children}
        </main>
      </div>
    </div>
  );
}
