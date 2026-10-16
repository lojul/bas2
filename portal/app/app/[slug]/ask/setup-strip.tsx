"use client";

import { useSyncExternalStore } from "react";
import Link from "next/link";
import { CheckCircle2, Circle, X } from "lucide-react";

// Setup checklist for owners and admins, as a slim strip above Ask. Hidden when everything is done
// or once closed in this browser.
export type SetupStep = { done: boolean; text: string; href: string };

const listeners = new Set<() => void>();
const subscribe = (cb: () => void) => {
  listeners.add(cb);
  window.addEventListener("storage", cb);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("storage", cb);
  };
};

export function SetupStrip({ slug, steps }: { slug: string; steps: SetupStep[] }) {
  const key = `genie.setup.closed.${slug}`;
  const closed = useSyncExternalStore(
    subscribe,
    () => {
      try {
        return localStorage.getItem(key) === "1";
      } catch {
        return false;
      }
    },
    () => true,
  );
  const done = steps.filter((s) => s.done).length;
  if (closed || done === steps.length) return null;

  return (
    <div className="flex items-start gap-3 rounded-lg border border-genie-border px-4 py-3 text-sm">
      <div className="min-w-0 flex-1">
        <p className="font-medium">
          Set up {done} of {steps.length} done
        </p>
        <ul className="mt-1.5 flex flex-wrap gap-x-5 gap-y-1">
          {steps.map((s) => (
            <li key={s.text} className="flex items-center gap-1.5">
              {s.done ? <CheckCircle2 size={15} className="text-genie-green" /> : <Circle size={15} className="text-genie-muted" />}
              {s.done ? (
                <span className="text-genie-muted line-through">{s.text}</span>
              ) : (
                <Link href={s.href} className="hover:underline">
                  {s.text}
                </Link>
              )}
            </li>
          ))}
        </ul>
      </div>
      <button
        type="button"
        aria-label="Close"
        className="rounded p-0.5 text-genie-muted hover:bg-genie-accent"
        onClick={() => {
          try {
            localStorage.setItem(key, "1");
          } catch {
            // Private window: shows again next time.
          }
          listeners.forEach((l) => l());
        }}
      >
        <X size={14} />
      </button>
    </div>
  );
}
