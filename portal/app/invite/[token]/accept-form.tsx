"use client";

import { useActionState } from "react";
import { FormMessage } from "@/components/form-message";
import { SubmitButton } from "@/components/submit-button";
import { acceptInvitation, createAccountAndJoin } from "./actions";

export function AcceptForm({ token }: { token: string }) {
  const [state, action] = useActionState(acceptInvitation, undefined);
  return (
    <form action={action}>
      <input type="hidden" name="token" value={token} />
      <SubmitButton pendingText="Joining…" className="btn w-full">Accept invitation</SubmitButton>
      <FormMessage state={state} />
    </form>
  );
}

// Invitee without an account: choose a password for the invited email and join in one step.
export function CreatePasswordForm({ token, email }: { token: string; email: string }) {
  const [state, action] = useActionState(createAccountAndJoin, undefined);
  return (
    <form action={action} className="space-y-3">
      <input type="hidden" name="token" value={token} />
      <div>
        <label className="label" htmlFor="email">Email</label>
        <input id="email" className="input" value={email} readOnly disabled />
      </div>
      <div>
        <label className="label" htmlFor="password">Choose a password</label>
        <input id="password" name="password" type="password" autoComplete="new-password" minLength={8} required className="input" />
      </div>
      <div>
        <label className="label" htmlFor="repeat">Repeat password</label>
        <input id="repeat" name="repeat" type="password" autoComplete="new-password" minLength={8} required className="input" />
        <p className="mt-1 text-xs text-genie-muted">At least 8 characters.</p>
      </div>
      <SubmitButton pendingText="Creating your account…" className="btn w-full">Create account and join</SubmitButton>
      <FormMessage state={state} />
    </form>
  );
}
