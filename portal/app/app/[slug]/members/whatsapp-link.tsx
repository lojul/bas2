"use client";

import { useActionState } from "react";
import { SubmitButton } from "@/components/submit-button";
import { BRAND } from "@/lib/brand";
import { type LinkState, startWhatsAppLink, unlinkWhatsApp } from "./whatsapp-actions";

// Members → Your WhatsApp. Linked: the number and Unlink. Not linked: a code to send from the phone.
export function WhatsAppLinkCard({ slug, number, linkedPhone }: { slug: string; number: string; linkedPhone: string | null }) {
  const [state, action] = useActionState<LinkState, FormData>(startWhatsAppLink, undefined);
  const digits = number.replace(/\D/g, "");

  if (linkedPhone) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm">
          Linked: <b>{linkedPhone}</b> <span className="text-genie-muted">· ask on WhatsApp at {number}</span>
        </p>
        <form
          action={unlinkWhatsApp}
          onSubmit={(e) => {
            if (!confirm("Unlink this WhatsApp number? " + BRAND.name + " will stop answering it.")) e.preventDefault();
          }}
        >
          <input type="hidden" name="slug" value={slug} />
          <SubmitButton className="btn-danger" pendingText="…">Unlink</SubmitButton>
        </form>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-genie-muted">Not linked. {BRAND.name}{" "}only answers WhatsApp numbers linked to a member.</p>
      {state?.code ? (
        <div className="space-y-2 rounded-lg bg-genie-accent/60 p-4 text-sm">
          <p>
            From your phone, send <b className="font-mono">LINK {state.code}</b> on WhatsApp to <b>{number}</b> before{" "}
            {new Date(state.expiresAt!).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}.
          </p>
          <a className="btn-secondary inline-block" href={`https://wa.me/${digits}?text=${encodeURIComponent(`LINK ${state.code}`)}`} target="_blank" rel="noreferrer">
            Open WhatsApp
          </a>
          <p className="text-xs text-genie-muted">Twilio Sandbox: send the Sandbox&apos;s &quot;join …&quot; phrase first. Reload this page after {BRAND.name}{" "}replies.</p>
        </div>
      ) : (
        <form action={action}>
          <input type="hidden" name="slug" value={slug} />
          <SubmitButton pendingText="…">Link WhatsApp</SubmitButton>
        </form>
      )}
      {state?.error && <p className="text-sm text-genie-danger">{state.error}</p>}
    </div>
  );
}
