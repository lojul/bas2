"use client";

import { useActionState, useState } from "react";
import { Copy, Check } from "lucide-react";
import { FormMessage } from "@/components/form-message";
import { SubmitButton } from "@/components/submit-button";
import { inviteMember, renewInvitation } from "./actions";

export function InviteForm({ slug }: { slug: string }) {
  const [state, action] = useActionState(inviteMember, undefined);
  const [copied, setCopied] = useState(false);

  return (
    <div>
      <form action={action} className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <input type="hidden" name="slug" value={slug} />
        <div className="flex-1">
          <label htmlFor="invite-email" className="label">Email</label>
          <input id="invite-email" name="email" type="email" required className="input" placeholder="colleague@company.com" />
        </div>
        <div>
          <label htmlFor="invite-role" className="label">Role</label>
          <select id="invite-role" name="role" defaultValue="member" className="input">
            <option value="admin">Admin</option>
            <option value="member">Member</option>
            <option value="viewer">Viewer</option>
          </select>
        </div>
        <SubmitButton pendingText="Creating…">Create invite link</SubmitButton>
      </form>
      <FormMessage state={state} />
      {state?.link && (
        <div className="mt-2 flex items-center gap-2">
          <input readOnly value={state.link} className="input font-mono text-xs" onFocus={(e) => e.target.select()} />
          <button
            type="button"
            className="btn-secondary shrink-0"
            onClick={async () => {
              await navigator.clipboard.writeText(state.link!);
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            }}
          >
            {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? "Copied" : "Copy"}
          </button>
        </div>
      )}
    </div>
  );
}

// "New link" for a pending or expired invitation, with the link to copy.
export function RenewInvite({ slug, id }: { slug: string; id: string }) {
  const [state, action, pending] = useActionState(renewInvitation, undefined);
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex flex-col items-end gap-2">
      <form action={action}>
        <input type="hidden" name="slug" value={slug} />
        <input type="hidden" name="id" value={id} />
        <button type="submit" className="btn-secondary px-3 py-1" disabled={pending}>
          {pending ? "Creating…" : "New link"}
        </button>
      </form>
      {state?.error && <p className="text-xs text-genie-danger">{state.error}</p>}
      {state?.link && (
        <div className="flex w-full max-w-md items-center gap-2">
          <code className="input min-w-0 flex-1 truncate font-mono text-xs">{state.link}</code>
          <button
            type="button"
            className="btn-secondary shrink-0 px-3 py-1"
            onClick={async () => {
              await navigator.clipboard.writeText(state.link!);
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            }}
          >
            {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? "Copied" : "Copy"}
          </button>
        </div>
      )}
    </div>
  );
}
