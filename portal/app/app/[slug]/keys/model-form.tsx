"use client";

import { useActionState, useState } from "react";
import { FormMessage } from "@/components/form-message";
import { SubmitButton } from "@/components/submit-button";
import type { ModelOption, RouteProvider } from "@/lib/ai/models";
import { saveModel } from "./actions";

// "Model for Ask": pick from the list for the key in use, or type any model id.
export function ModelForm({ slug, provider, options, current }: { slug: string; provider: RouteProvider; options: ModelOption[]; current: string }) {
  const [state, action] = useActionState(saveModel, undefined);
  const inList = options.some((o) => o.id === current);
  const [choice, setChoice] = useState(inList ? current : "custom");
  return (
    <form action={action} className="space-y-3">
      <input type="hidden" name="slug" value={slug} />
      <input type="hidden" name="provider" value={provider} />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex-1">
          <label htmlFor="model" className="label">Model</label>
          <select id="model" name="model" className="input" value={choice} onChange={(e) => setChoice(e.target.value)}>
            {options.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
                {o.note ? ` — ${o.note}` : ""}
              </option>
            ))}
            <option value="custom">Other (type a model id)…</option>
          </select>
        </div>
        {choice === "custom" && (
          <div className="flex-1">
            <label htmlFor="custom_model" className="label">Model id</label>
            <input id="custom_model" name="custom_model" className="input font-mono" defaultValue={inList ? "" : current} placeholder="e.g. qwen/qwen3.8-flash" required />
          </div>
        )}
        <SubmitButton pendingText="Saving…">Save model</SubmitButton>
      </div>
      <FormMessage state={state} />
    </form>
  );
}
