"use client";

import { startTransition, useActionState, useState } from "react";
import { FormMessage } from "@/components/form-message";
import { SubmitButton } from "@/components/submit-button";
import { type OdooModelChoice, guessOdooDb } from "@/lib/sync/models";
import { connectOdoo, syncSource } from "./actions";

export function OdooForm({ slug, choices }: { slug: string; choices: OdooModelChoice[] }) {
  const [state, action, pending] = useActionState(connectOdoo, undefined);
  const [url, setUrl] = useState("");
  // Hide the last result as soon as the user changes something, so an old error doesn't linger.
  const [stale, setStale] = useState(false);
  const guessedDb = guessOdooDb(url.startsWith("http") ? url : `https://${url}`);
  const needsDb = url.trim() !== "" && !guessedDb;
  return (
    <form
      className="space-y-3"
      onChange={() => setStale(true)}
      // Submit without React's automatic form reset, so typed values (and the API key) survive an error.
      onSubmit={(e) => {
        e.preventDefault();
        const data = new FormData(e.currentTarget);
        setStale(false);
        startTransition(() => action(data));
      }}
    >
      <input type="hidden" name="slug" value={slug} />
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="url" className="label">Odoo address</label>
          <input id="url" name="url" required className="input" placeholder="https://yourcompany.odoo.com" value={url} onChange={(e) => setUrl(e.target.value)} />
          <p className="mt-1 text-xs text-genie-muted">The address you open Odoo at in the browser.</p>
        </div>
        <div>
          <label htmlFor="api_key" className="label">API key</label>
          <input id="api_key" name="api_key" type="password" autoComplete="off" required className="input font-mono" placeholder="Paste the Odoo API key" />
          <p className="mt-1 text-xs text-genie-muted">In Odoo: your avatar → Preferences → Account Security → New API Key.</p>
        </div>
        {/* Odoo Online (<name>.odoo.com) needs no database name; only self-hosted Odoo asks for it. */}
        {needsDb && (
          <div>
            <label htmlFor="db" className="label">Database name</label>
            <input id="db" name="db" required className="input" placeholder="yourcompany" />
            <p className="mt-1 text-xs text-genie-muted">Your own Odoo server can hold several databases — ask your Odoo administrator which one.</p>
          </div>
        )}
        <div>
          <label htmlFor="name" className="label">Name in Genie</label>
          <input id="name" name="name" className="input" defaultValue="Odoo" />
        </div>
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-genie-muted">Using Odoo 18 or older?</summary>
        <div className="mt-2 max-w-md">
          <label htmlFor="login" className="label">Login email of the Odoo user</label>
          <input id="login" name="login" type="email" className="input" placeholder="integration@yourcompany.com" />
          <p className="mt-1 text-xs text-genie-muted">Older Odoo versions need the login together with the API key. Leave empty for Odoo 19 or newer.</p>
        </div>
      </details>
      <fieldset>
        <legend className="label">What to copy into Genie</legend>
        <div className="grid gap-2 sm:grid-cols-3">
          {choices.map((c) => (
            <label key={c.model} className="flex cursor-pointer items-start gap-2 rounded-lg border border-genie-border bg-white p-3 text-sm has-[:checked]:border-genie-green">
              <input type="checkbox" name="models" value={c.model} defaultChecked className="mt-0.5 accent-genie-green" />
              <span>
                <span className="block font-medium">{c.label}</span>
                <span className="block text-xs text-genie-muted">{c.hint}</span>
              </span>
            </label>
          ))}
        </div>
        <details className="mt-2 text-sm">
          <summary className="cursor-pointer text-genie-muted">More Odoo data (advanced)</summary>
          <label htmlFor="extra_models" className="mt-2 block text-xs text-genie-muted">
            Odoo&apos;s internal names, separated by commas — e.g. <span className="font-mono">sale.order, product.template</span>. Your Odoo administrator can find them under Settings → Technical → Models.
          </label>
          <input id="extra_models" name="extra_models" className="input mt-1 font-mono" placeholder="sale.order, product.template" />
        </details>
      </fieldset>
      <button type="submit" className="btn" disabled={pending}>
        {pending ? "Checking the connection…" : "Connect and save"}
      </button>
      <p className="text-xs text-genie-muted">Genie checks the address and key with Odoo, then saves them. Nothing is copied until you press Sync now.</p>
      {!stale && <FormMessage state={state} />}
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
