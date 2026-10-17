"use client";

import { useState } from "react";
import { Check, ExternalLink, PencilLine, X } from "lucide-react";
import type { ProposalView } from "@/lib/odoo/changes";
import { decideProposal } from "./actions";

// A draft change in Odoo under Genie's answer. Nothing is written until Confirm (user decision
// 2026-10-17); only the person who asked, or an owner/admin, can confirm or cancel.
export function ProposalCard({ slug, view, onChange }: { slug: string; view: ProposalView; onChange: (v: ProposalView) => void }) {
  const [busy, setBusy] = useState<"confirm" | "cancel" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function decide(confirm: boolean) {
    setBusy(confirm ? "confirm" : "cancel");
    setError(null);
    const res = await decideProposal(slug, view.id, confirm);
    setBusy(null);
    if (res.ok) onChange(res.view);
    else setError(res.error);
  }

  const status: Record<ProposalView["status"], { text: string; cls: string }> = {
    proposed: { text: "Draft — not saved in Odoo yet", cls: "text-amber-700" },
    done: { text: `Saved in Odoo${view.decided_email ? ` · confirmed by ${view.decided_email}` : ""}`, cls: "text-genie-green" },
    cancelled: { text: "Cancelled — nothing was changed in Odoo", cls: "text-genie-muted" },
    expired: { text: "Expired after 24 hours — nothing was changed in Odoo", cls: "text-genie-muted" },
    failed: { text: "Odoo refused the change", cls: "text-genie-danger" },
  };

  return (
    <div className={`mt-3 rounded-lg border p-4 ${view.status === "proposed" ? "border-amber-300 bg-amber-50/40" : "border-genie-border bg-white"}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 font-medium">
          <PencilLine size={16} /> {view.label}
          {view.title && view.status !== "proposed" ? <span className="font-normal text-genie-muted">· {view.title}</span> : null}
        </p>
        <span className={`text-sm ${status[view.status].cls}`}>{status[view.status].text}</span>
      </div>
      {view.lines.length > 0 && (
        <dl className="mt-3 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]">
          {view.lines.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-genie-muted">{k}</dt>
              <dd className="whitespace-pre-wrap">{v}</dd>
            </div>
          ))}
        </dl>
      )}
      {view.status === "proposed" && !view.canDecide && (
        <p className="mt-3 text-sm text-genie-muted">Waiting for {view.requested_email ?? "the person who asked"} to confirm.</p>
      )}
      {view.error && view.status === "failed" && <p className="mt-2 text-sm text-genie-danger">{view.error}</p>}
      {error && <p className="mt-2 text-sm text-genie-danger">{error}</p>}
      <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
        {view.link && (
          <a href={view.link} target="_blank" rel="noreferrer" className="mr-auto inline-flex items-center gap-1 text-sm underline underline-offset-2">
            Open in Odoo <ExternalLink size={13} />
          </a>
        )}
        {view.canDecide && (
          <>
            <button type="button" className="btn-secondary" disabled={!!busy} onClick={() => decide(false)}>
              <X size={15} /> {busy === "cancel" ? "Cancelling…" : "Cancel"}
            </button>
            <button type="button" className="btn" disabled={!!busy} onClick={() => decide(true)}>
              <Check size={15} /> {busy === "confirm" ? "Saving in Odoo…" : "Confirm"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
