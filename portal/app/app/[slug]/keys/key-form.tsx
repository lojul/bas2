"use client";

import { useActionState } from "react";
import { FormMessage } from "@/components/form-message";
import { SubmitButton } from "@/components/submit-button";
import { AI_PROVIDERS } from "@/lib/providers";
import { saveAiKey } from "./actions";

export function KeyForm({ slug }: { slug: string }) {
  const [state, action] = useActionState(saveAiKey, undefined);
  return (
    <form action={action}>
      <input type="hidden" name="slug" value={slug} />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div>
          <label htmlFor="provider" className="label">Provider</label>
          <select id="provider" name="provider" className="input" defaultValue="anthropic">
            {AI_PROVIDERS.map((p) => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
          </select>
        </div>
        <div className="flex-1">
          <label htmlFor="key" className="label">API key</label>
          <input id="key" name="key" type="password" autoComplete="off" required className="input font-mono" placeholder="Paste the key" />
        </div>
        <SubmitButton pendingText="Saving…">Save key</SubmitButton>
      </div>
      <FormMessage state={state} />
    </form>
  );
}
