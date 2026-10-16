"use client";

import { useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ArrowRight,
  ChevronsUpDown,
  CircleHelp,
  KeyRound,
  LayoutDashboard,
  LayoutGrid,
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
    <div className="relative rounded-xl bg-white/10 p-3 text-xs text-white/80">
      <button type="button" onClick={close} className="absolute right-2 top-2 rounded p-0.5 hover:bg-white/10" aria-label="Close">
        <X size={14} />
      </button>
      <div className="flex items-center gap-2">
        <span className="rounded bg-genie-lime px-1.5 py-0.5 text-[10px] font-semibold text-genie-ink">NEW</span>
        <span>{WHATS_NEW.date}</span>
      </div>
      <p className="mt-2 font-semibold text-white">{WHATS_NEW.title}</p>
      <p className="mt-1 leading-relaxed">{WHATS_NEW.text}</p>
      <Link href={`/app/${slug}${WHATS_NEW.path}`} onClick={onNavigate} className="mt-2 inline-flex items-center gap-1 font-medium text-genie-lime">
        See what&apos;s new <ArrowRight size={12} />
      </Link>
    </div>
  );
}

function SidebarBody({
  workspace,
  workspaces,
  email,
  source,
  onNavigate,
}: {
  workspace: ShellWorkspace;
  workspaces: ShellWorkspace[];
  email: string;
  source: SourceStatus;
  onNavigate: () => void;
}) {
  const pathname = usePathname();
  const active = activeNav(pathname, workspace.slug);
  const items = NAV.filter((n) => !n.managersOnly || canManage(workspace.role));
  const base = `/app/${workspace.slug}`;
  const sourceOk = source && source.status !== "error";

  return (
    <div className="flex h-full flex-col gap-4 px-3 py-4">
      <Link href={base} onClick={onNavigate} className="flex items-center gap-2 px-2 text-lg font-semibold text-white">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-genie-lime text-genie-ink">
          <Sparkles size={15} />
        </span>
        {BRAND.name}
        <span className="rounded bg-genie-lime px-1.5 py-0.5 text-[10px] font-semibold text-genie-ink">BETA</span>
      </Link>

      {/* Workspace switcher */}
      <details className="group relative">
        <summary className="flex cursor-pointer list-none items-center justify-between rounded-lg border border-white/15 px-3 py-2 text-sm text-white hover:bg-white/10">
          <span className="min-w-0">
            <span className="block truncate font-medium">{workspace.name}</span>
            <span className="block text-xs text-white/60">{ROLE_LABEL[workspace.role]}</span>
          </span>
          <ChevronsUpDown size={14} className="shrink-0 text-white/60" />
        </summary>
        <div className="absolute inset-x-0 z-20 mt-1 rounded-lg border border-genie-border bg-genie-card p-1 text-sm text-genie-ink shadow-lg">
          {workspaces.map((w) => (
            <Link
              key={w.slug}
              href={`/app/${w.slug}`}
              onClick={onNavigate}
              className={`block truncate rounded-md px-3 py-2 hover:bg-genie-bg ${w.slug === workspace.slug ? "font-medium" : ""}`}
            >
              {w.name}
            </Link>
          ))}
          <div className="my-1 h-px bg-genie-border" />
          <Link href="/app" onClick={onNavigate} className="flex items-center gap-2 rounded-md px-3 py-2 hover:bg-genie-bg">
            <LayoutGrid size={14} /> All workspaces
          </Link>
          <Link href="/app/new" onClick={onNavigate} className="flex items-center gap-2 rounded-md px-3 py-2 hover:bg-genie-bg">
            <Plus size={14} /> New workspace
          </Link>
        </div>
      </details>

      <nav className="space-y-1">
        {items.map((item) => {
          const Icon = ICONS[item.key];
          const on = item.key === active.key;
          return (
            <Link
              key={item.key}
              href={`${base}${item.path}`}
              onClick={onNavigate}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm ${
                on ? "bg-genie-lime font-medium text-genie-ink" : "text-white/80 hover:bg-white/10 hover:text-white"
              }`}
            >
              <Icon size={16} /> {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto space-y-3">
        <WhatsNew slug={workspace.slug} onNavigate={onNavigate} />

        <div className="flex items-start gap-2 px-2 text-xs text-white/70">
          <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${source ? (sourceOk ? "bg-genie-lime" : "bg-red-400") : "bg-white/30"}`} />
          {source ? (
            <span>
              <span className="text-white">{source.name}</span>
              <br />
              {source.status === "error" ? "Can't reach it — see Settings" : "On · read live"}
            </span>
          ) : (
            <span>No data source connected</span>
          )}
        </div>

        {/* Account menu (opens upwards) */}
        <details className="relative">
          <summary className="flex cursor-pointer list-none items-center gap-2 rounded-lg px-2 py-2 text-sm text-white hover:bg-white/10">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white/15 text-xs font-semibold uppercase">
              {email.slice(0, 1)}
            </span>
            <span className="min-w-0 flex-1 truncate">{email}</span>
            <ChevronsUpDown size={14} className="shrink-0 text-white/60" />
          </summary>
          <div className="absolute inset-x-0 bottom-full z-20 mb-1 rounded-lg border border-genie-border bg-genie-card p-1 text-sm text-genie-ink shadow-lg">
            <Link href="/reset-password" onClick={onNavigate} className="flex items-center gap-2 rounded-md px-3 py-2 hover:bg-genie-bg">
              <KeyRound size={14} /> Change password
            </Link>
            <form action="/auth/signout" method="post">
              <button type="submit" className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left hover:bg-genie-bg">
                <LogOut size={14} /> Sign out
              </button>
            </form>
          </div>
        </details>
      </div>
    </div>
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
  const [open, setOpen] = useState(false);
  const page = activeNav(pathname, workspace.slug);
  const body = (
    <SidebarBody workspace={workspace} workspaces={workspaces} email={email} source={source} onNavigate={() => setOpen(false)} />
  );

  return (
    <div className="flex flex-1">
      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 bg-genie-green-deep md:block">{body}</aside>

      {/* Mobile drawer */}
      {open && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button type="button" className="absolute inset-0 bg-black/40" aria-label="Close menu" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 max-w-[85vw] overflow-y-auto bg-genie-green-deep">{body}</aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-genie-border bg-genie-card px-4 py-3 md:hidden">
          <button type="button" onClick={() => setOpen(true)} className="rounded-md p-1 hover:bg-genie-bg" aria-label="Open menu">
            <Menu size={20} />
          </button>
          <span className="truncate font-medium">{workspace.name}</span>
        </header>
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:px-8 sm:py-8">
          <h1 className="text-2xl font-semibold">{page.title}</h1>
          <p className="mt-1 text-sm text-genie-muted">{page.subtitle}</p>
          <div className="mt-6">{children}</div>
        </main>
      </div>
    </div>
  );
}
