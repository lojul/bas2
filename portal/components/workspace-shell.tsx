"use client";

import { useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  ArrowUpRight,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  KeyRound,
  LayoutDashboard,
  LayoutGrid,
  LogOut,
  Menu,
  MessagesSquare,
  Plus,
  Search,
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

const ICONS: Record<NavKey, typeof LayoutDashboard> = {
  overview: LayoutDashboard,
  ask: MessagesSquare,
  members: Users,
  settings: Settings,
  help: CircleHelp,
};

export type ShellWorkspace = { slug: string; name: string; role: Role };
export type SourceStatus = { name: string; status: string } | null;

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

function Sidebar({ workspace, source, onNavigate }: { workspace: ShellWorkspace; source: SourceStatus; onNavigate: () => void }) {
  const pathname = usePathname();
  const active = activeNav(pathname, workspace.slug);
  const items = NAV.filter((n) => !n.managersOnly || canManage(workspace.role));
  const base = `/app/${workspace.slug}`;
  const sourceOk = source && source.status !== "error";

  return (
    <div className="flex h-full flex-col gap-4 py-4">
      <div>
        <p className="mb-1 flex items-center gap-1 px-2 text-[11px] font-medium uppercase tracking-wide text-genie-muted">
          <ChevronDown size={12} /> Workspace
        </p>
        <nav className="space-y-px">
          {items.map((item) => {
            const Icon = ICONS[item.key];
            const on = item.key === active.key;
            return (
              <Link
                key={item.key}
                href={`${base}${item.path}`}
                onClick={onNavigate}
                className={`flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm ${
                  on ? "bg-genie-accent font-medium text-genie-ink" : "text-genie-ink/80 hover:bg-genie-accent"
                }`}
              >
                <Icon size={15} strokeWidth={1.75} className="text-genie-muted" /> {item.label}
              </Link>
            );
          })}
        </nav>
      </div>

      <div>
        <p className="mb-1 px-2 text-[11px] font-medium uppercase tracking-wide text-genie-muted">Data sources</p>
        <Link
          href={`${base}/settings#data-sources`}
          onClick={onNavigate}
          className="flex items-start gap-2 rounded-md px-2 py-1.5 text-xs text-genie-muted hover:bg-genie-accent"
        >
          <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${source ? (sourceOk ? "bg-genie-green" : "bg-genie-danger") : "bg-gray-300"}`} />
          {source ? (
            <span>
              <span className="text-genie-ink">{source.name}</span>
              <br />
              {source.status === "error" ? "Can't reach it — see Settings" : "On · read live"}
            </span>
          ) : (
            <span>None switched on</span>
          )}
        </Link>
      </div>

      <div className="mt-auto">
        <WhatsNew slug={workspace.slug} onNavigate={onNavigate} />
      </div>
    </div>
  );
}

function AccountMenu({ email, slug }: { email: string; slug: string }) {
  return (
    <details className="relative">
      <summary
        className="flex h-7 w-7 cursor-pointer list-none items-center justify-center rounded-full bg-genie-accent text-xs font-semibold uppercase text-genie-ink"
        title={email}
      >
        {email.slice(0, 1)}
      </summary>
      <div className="absolute right-0 z-40 mt-2 w-60 rounded-lg border border-genie-border bg-white p-1 text-sm shadow-lg">
        <p className="truncate px-3 py-2 text-xs text-genie-muted">{email}</p>
        <Link href="/reset-password" className="flex items-center gap-2 rounded-md px-3 py-1.5 hover:bg-genie-accent">
          <KeyRound size={14} /> Change password
        </Link>
        <Link href={`/app/${slug}/help`} className="flex items-center gap-2 rounded-md px-3 py-1.5 hover:bg-genie-accent">
          <CircleHelp size={14} /> Help
        </Link>
        <form action="/auth/signout" method="post">
          <button type="submit" className="flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-left hover:bg-genie-accent">
            <LogOut size={14} /> Sign out
          </button>
        </form>
      </div>
    </details>
  );
}

function WorkspaceSwitcher({ workspace, workspaces }: { workspace: ShellWorkspace; workspaces: ShellWorkspace[] }) {
  return (
    <details className="relative">
      <summary className="flex cursor-pointer list-none items-center gap-1 rounded-md px-1.5 py-1 text-sm text-genie-ink hover:bg-genie-accent">
        <span className="max-w-[12rem] truncate">{workspace.name}</span>
        <ChevronDown size={13} className="text-genie-muted" />
      </summary>
      <div className="absolute left-0 z-40 mt-2 w-64 rounded-lg border border-genie-border bg-white p-1 text-sm shadow-lg">
        {workspaces.map((w) => (
          <Link
            key={w.slug}
            href={`/app/${w.slug}`}
            className={`flex items-center justify-between rounded-md px-3 py-1.5 hover:bg-genie-accent ${w.slug === workspace.slug ? "font-medium" : ""}`}
          >
            <span className="truncate">{w.name}</span>
            <span className="text-xs text-genie-muted">{ROLE_LABEL[w.role]}</span>
          </Link>
        ))}
        <div className="my-1 h-px bg-genie-border" />
        <Link href="/app" className="flex items-center gap-2 rounded-md px-3 py-1.5 hover:bg-genie-accent">
          <LayoutGrid size={14} /> All workspaces
        </Link>
        <Link href="/app/new" className="flex items-center gap-2 rounded-md px-3 py-1.5 hover:bg-genie-accent">
          <Plus size={14} /> New workspace
        </Link>
      </div>
    </details>
  );
}

// "Search or ask Genie" box, like ERPNext's awesome bar: Enter opens Ask with the question filled in.
function CommandBox({ slug }: { slug: string }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  return (
    <form
      className="relative hidden w-72 sm:block"
      onSubmit={(e) => {
        e.preventDefault();
        if (q.trim()) router.push(`/app/${slug}/ask?q=${encodeURIComponent(q.trim())}`);
        setQ("");
      }}
    >
      <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-genie-muted" />
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={`Search or ask ${BRAND.name}…`}
        className="input h-8 pl-8"
        aria-label={`Search or ask ${BRAND.name}`}
      />
    </form>
  );
}

export function WorkspaceShell({
  workspace,
  workspaces,
  email,
  source,
  children,
}: {
  workspace: ShellWorkspace;
  workspaces: ShellWorkspace[];
  email: string;
  source: SourceStatus;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [drawer, setDrawer] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const page = activeNav(pathname, workspace.slug);
  const base = `/app/${workspace.slug}`;

  return (
    <div className="flex min-h-screen flex-col bg-white">
      <header className="sticky top-0 z-30 border-b border-genie-border bg-white">
        <div className="mx-auto flex h-12 max-w-7xl items-center gap-2 px-4">
          <Link href={base} className="mr-1 flex h-7 w-7 items-center justify-center rounded-md bg-genie-green-deep text-white" aria-label={BRAND.name}>
            <Sparkles size={14} />
          </Link>
          <ChevronRight size={14} className="text-genie-muted" />
          <WorkspaceSwitcher workspace={workspace} workspaces={workspaces} />
          {page.key !== "overview" && (
            <>
              <ChevronRight size={14} className="text-genie-muted" />
              <span className="truncate text-sm text-genie-muted">{page.title}</span>
            </>
          )}
          <div className="ml-auto flex items-center gap-3">
            <CommandBox slug={workspace.slug} />
            <Link href={`${base}/help`} className="hidden text-sm text-genie-ink hover:underline sm:inline">
              Help
            </Link>
            <AccountMenu email={email} slug={workspace.slug} />
          </div>
        </div>
      </header>

      {/* Phone drawer */}
      {drawer && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button type="button" className="absolute inset-0 bg-black/30" aria-label="Close menu" onClick={() => setDrawer(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 max-w-[85vw] overflow-y-auto bg-white px-3">
            <Sidebar workspace={workspace} source={source} onNavigate={() => setDrawer(false)} />
          </aside>
        </div>
      )}

      <div className="mx-auto flex w-full max-w-7xl flex-1 px-4">
        {!collapsed && (
          <aside className="sticky top-12 hidden h-[calc(100vh-3rem)] w-56 shrink-0 overflow-y-auto pr-4 md:block">
            <Sidebar workspace={workspace} source={source} onNavigate={() => {}} />
          </aside>
        )}
        <main className={`min-w-0 flex-1 py-4 ${collapsed ? "" : "md:pl-4"}`}>
          <div className="mb-5 flex items-center gap-2">
            <button
              type="button"
              className="rounded-md p-1 text-genie-muted hover:bg-genie-accent"
              aria-label="Toggle sidebar"
              onClick={() => (window.matchMedia("(min-width: 768px)").matches ? setCollapsed(!collapsed) : setDrawer(true))}
            >
              <Menu size={18} />
            </button>
            <div className="min-w-0">
              <h1 className="truncate text-xl font-semibold text-genie-ink">{page.title}</h1>
            </div>
          </div>
          <p className="-mt-3 mb-5 pl-9 text-sm text-genie-muted">{page.subtitle}</p>
          {children}
        </main>
      </div>
    </div>
  );
}
