"use client";

import { useSyncExternalStore } from "react";

// ERPNext-style tabs for the Settings page. The open tab follows the address's #fragment
// (#data-sources, #ai-keys, #ai-agents), so existing links and the back button keep working.
type Tab = { id: string; title: string; hint: string };

const subscribe = (cb: () => void) => {
  window.addEventListener("hashchange", cb);
  return () => window.removeEventListener("hashchange", cb);
};

export function SettingsTabs({ tabs, panels }: { tabs: Tab[]; panels: Record<string, React.ReactNode> }) {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash.slice(1), () => "");
  const active = tabs.find((t) => t.id === hash) ?? tabs[0];

  return (
    <div>
      <nav className="mb-6 flex gap-6 border-b border-genie-border text-sm" role="tablist">
        {tabs.map((t) => {
          const on = t.id === active.id;
          return (
            <a
              key={t.id}
              href={`#${t.id}`}
              role="tab"
              aria-selected={on}
              className={`-mb-px border-b-2 py-2.5 ${on ? "border-genie-ink font-medium text-genie-ink" : "border-transparent text-genie-muted hover:text-genie-ink"}`}
            >
              {t.title}
            </a>
          );
        })}
      </nav>
      <p className="mb-5 text-sm text-genie-muted">{active.hint}</p>
      {/* All panels are rendered on the server; only the open one is shown. */}
      {tabs.map((t) => (
        <section key={t.id} id={`panel-${t.id}`} role="tabpanel" hidden={t.id !== active.id} className="space-y-4">
          {panels[t.id]}
        </section>
      ))}
    </div>
  );
}
