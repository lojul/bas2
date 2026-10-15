"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function WorkspaceTabs({ slug, showKeys }: { slug: string; showKeys: boolean }) {
  const pathname = usePathname();
  const base = `/app/${slug}`;
  const tabs = [
    { href: base, label: "Overview" },
    { href: `${base}/ask`, label: "Ask" },
    { href: `${base}/members`, label: "Members" },
    ...(showKeys
      ? [
          { href: `${base}/keys`, label: "AI keys" },
          { href: `${base}/agents`, label: "AI agents (MCP)" },
        ]
      : []),
  ];
  return (
    <nav className="mt-4 flex gap-1 border-b border-genie-border">
      {tabs.map((t) => {
        const active = t.href === base ? pathname === base : pathname.startsWith(t.href);
        return (
          <Link
            key={t.href}
            href={t.href}
            className={`-mb-px border-b-2 px-3 py-2 text-sm ${
              active ? "border-genie-green-deep font-medium" : "border-transparent text-genie-muted hover:text-genie-ink"
            }`}
          >
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
