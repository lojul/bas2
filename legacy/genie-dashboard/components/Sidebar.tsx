"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearToken } from "@/lib/api";

interface NavItem {
  href: string;
  label: string;
}

const mainNav: NavItem[] = [
  { href: "/chat",         label: "Chat" },
  { href: "/search",       label: "Keyword Search" },
  { href: "/admin/ingest", label: "Ingest" },
];

const adminNav: NavItem[] = [
  { href: "/admin/process",  label: "Processing" },
  { href: "/admin/vector",   label: "Vector DB" },
  { href: "/admin/settings", label: "Settings" },
];

function NavLink({
  href,
  label,
  pathname,
  onClose,
}: NavItem & { pathname: string; onClose?: () => void }) {
  const active = pathname === href || pathname.startsWith(href + "/");
  return (
    <Link
      href={href}
      onClick={onClose}
      className={`block text-sm px-3 py-2 rounded-lg transition-colors ${
        active
          ? "bg-blue-50 text-blue-700 font-medium"
          : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
      }`}
    >
      {label}
    </Link>
  );
}

export function Sidebar({ onClose }: { onClose?: () => void }) {
  const pathname = usePathname();
  const router = useRouter();

  function handleLogout() {
    clearToken();
    onClose?.();
    router.replace("/login");
  }

  return (
    <aside className="w-52 shrink-0 bg-white border-r border-gray-200 flex flex-col h-full">
      <div className="px-4 py-4 border-b border-gray-100 flex items-center justify-between">
        <div>
          <p className="font-semibold text-gray-900 text-sm leading-snug">Property Intelligence</p>
          <p className="text-xs text-gray-400 mt-0.5">Century 21 Hong Kong</p>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors lg:hidden"
            aria-label="Close menu"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">
        {mainNav.map((item) => (
          <NavLink key={item.href} pathname={pathname} onClose={onClose} {...item} />
        ))}

        <div className="pt-4 pb-1 px-3">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Admin</p>
        </div>
        {adminNav.map((item) => (
          <NavLink key={item.href} pathname={pathname} onClose={onClose} {...item} />
        ))}
        <a
          href="https://smith.langchain.com"
          target="_blank"
          rel="noopener noreferrer"
          onClick={onClose}
          className="flex items-center justify-between text-sm px-3 py-2 rounded-lg text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition-colors"
        >
          <span>Logs (LangSmith)</span>
          <svg className="w-3 h-3 text-gray-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
          </svg>
        </a>
      </nav>

      <div className="p-3 border-t border-gray-100">
        <button
          onClick={handleLogout}
          className="w-full text-left text-sm text-gray-500 hover:text-gray-700 px-3 py-2 rounded-lg hover:bg-gray-50 transition-colors"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}
