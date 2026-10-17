"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

// ERPNext-style tabs for the Settings page. Each tab is its own address (?tab=…), so the server
// builds only the open tab. Old links with a #fragment (#data-sources, …) are moved to ?tab=.
type Tab = { id: string; title: string };

export function SettingsTabs({ slug, tabs, active }: { slug: string; tabs: Tab[]; active: string }) {
  const router = useRouter();
  useEffect(() => {
    const hash = window.location.hash.slice(1);
    if (hash && tabs.some((t) => t.id === hash) && hash !== active) router.replace(`/app/${slug}/settings?tab=${hash}`);
  }, [router, slug, tabs, active]);

  return (
    <nav className="mb-6 flex gap-6 overflow-x-auto border-b border-genie-border text-sm" role="tablist">
      {tabs.map((t) => {
        const on = t.id === active;
        return (
          <Link
            key={t.id}
            href={`/app/${slug}/settings?tab=${t.id}`}
            role="tab"
            aria-selected={on}
            scroll={false}
            className={`-mb-px whitespace-nowrap border-b-2 py-2.5 ${on ? "border-genie-ink font-medium text-genie-ink" : "border-transparent text-genie-muted hover:text-genie-ink"}`}
          >
            {t.title}
          </Link>
        );
      })}
    </nav>
  );
}
