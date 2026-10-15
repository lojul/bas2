"use client";

import { useActionState } from "react";
import { FormMessage } from "@/components/form-message";
import { SubmitButton } from "@/components/submit-button";
import { sendSignInLink } from "./actions";

export function LoginForm({ next }: { next: string }) {
  const [state, action] = useActionState(sendSignInLink, undefined);
  return (
    <form action={action}>
      <input type="hidden" name="next" value={next} />
      <label htmlFor="email" className="label">Work email</label>
      <input id="email" name="email" type="email" autoComplete="email" required className="input" placeholder="you@company.com" />
      <SubmitButton pendingText="Sending…" className="btn mt-4 w-full">Email me a sign-in link</SubmitButton>
      <FormMessage state={state} />
    </form>
  );
}
