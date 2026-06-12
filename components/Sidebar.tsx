"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearToken } from "@/lib/api";

interface NavItem {
  href: string;
  label: string;
}

const mainNav: NavItem[] = [
  { href: "/chat", label: "Chat" },
  { href: "/search", label: "Search" },
];

const adminNav: NavItem[] = [
  { href: "/admin/upload", label: "Upload" },
  { href: "/admin/process", label: "Processing" },
  { href: "/admin/vector", label: "Vector DB" },
];

function NavLink({ href, label, pathname }: NavItem & { pathname: string }) {
  const active = pathname === href || pathname.startsWith(href + "/");
  return (
    <Link
      href={href}
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

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  function handleLogout() {
    clearToken();
    router.replace("/login");
  }

  return (
    <aside className="w-52 shrink-0 bg-white border-r border-gray-200 flex flex-col h-full">
      <div className="px-4 py-4 border-b border-gray-100">
        <p className="font-semibold text-gray-900 text-sm leading-snug">Property Intelligence</p>
        <p className="text-xs text-gray-400 mt-0.5">Century 21 Hong Kong</p>
      </div>

      <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">
        {mainNav.map((item) => (
          <NavLink key={item.href} pathname={pathname} {...item} />
        ))}

        <div className="pt-4 pb-1 px-3">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Admin</p>
        </div>
        {adminNav.map((item) => (
          <NavLink key={item.href} pathname={pathname} {...item} />
        ))}
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
