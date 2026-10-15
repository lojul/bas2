"use client";

import { useActionState } from "react";
import { FormMessage } from "@/components/form-message";
import { SubmitButton } from "@/components/submit-button";
import { acceptInvitation } from "./actions";

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
