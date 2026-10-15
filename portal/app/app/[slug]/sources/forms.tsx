"use client";

import { useActionState } from "react";
import { FormMessage } from "@/components/form-message";
import { SubmitButton } from "@/components/submit-button";
import { connectOdoo, syncSource } from "./actions";

export function OdooForm({ slug, defaultModels }: { slug: string; defaultModels: string }) {
  const [state, action] = useActionState(connectOdoo, undefined);
  return (
    <form action={action} className="space-y-3">
      <input type="hidden" name="slug" value={slug} />
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="url" className="label">Odoo address</label>
          <input id="url" name="url" required className="input" placeholder="https://yourcompany.odoo.com" />
        </div>
        <div>
          <label htmlFor="db" className="label">Database name</label>
          <input id="db" name="db" required className="input" placeholder="yourcompany" />
        </div>
        <div>
          <label htmlFor="login" className="label">Login email <span className="font-normal text-genie-muted">(Odoo 18 or older)</span></label>
          <input id="login" name="login" type="email" className="input" placeholder="integration@yourcompany.com" />
        </div>
        <div>
          <label htmlFor="api_key" className="label">API key</label>
          <input id="api_key" name="api_key" type="password" autoComplete="off" required className="input font-mono" placeholder="Paste the Odoo API key" />
        </div>
        <div>
          <label htmlFor="name" className="label">Name in Genie</label>
          <input id="name" name="name" className="input" defaultValue="Odoo" />
        </div>
        <div>
          <label htmlFor="models" className="label">Odoo models to copy</label>
          <input id="models" name="models" className="input font-mono" defaultValue={defaultModels} />
        </div>
      </div>
      <SubmitButton pendingText="Checking the connection…">Connect</SubmitButton>
      <FormMessage state={state} />
    </form>
  );
}

export function SyncButton({ slug, sourceId }: { slug: string; sourceId: string }) {
  const [state, action] = useActionState(syncSource, undefined);
  return (
    <form action={action}>
      <input type="hidden" name="slug" value={slug} />
      <input type="hidden" name="source_id" value={sourceId} />
      <SubmitButton className="btn-secondary" pendingText="Syncing… (can take a minute)">Sync now</SubmitButton>
      <FormMessage state={state} />
    </form>
  );
}
