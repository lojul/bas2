"use client";

import { startTransition, useActionState, useState } from "react";
import { FormMessage } from "@/components/form-message";
import { BRAND } from "@/lib/brand";
import { guessOdooDb } from "@/lib/odoo/models";
import { connectOdoo, connectSearch, removeSource, testSource } from "./actions";

// Values of a saved source, for editing it in the same form.
export type OdooExisting = { id: string; url: string; db: string; name: string; login: string; extraModels: string };

export function OdooForm({ slug, existing }: { slug: string; existing?: OdooExisting }) {
  const [state, action, pending] = useActionState(connectOdoo, undefined);
  const [url, setUrl] = useState(existing?.url ?? "");
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
      {existing && <input type="hidden" name="source_id" value={existing.id} />}
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="url" className="label">Odoo address</label>
          <input id="url" name="url" required className="input" placeholder="https://yourcompany.odoo.com" value={url} onChange={(e) => setUrl(e.target.value)} />
          <p className="mt-1 text-xs text-genie-muted">The address you open Odoo at in the browser.</p>
        </div>
        <div>
          <label htmlFor="api_key" className="label">API key</label>
          <input
            id="api_key"
            name="api_key"
            type="password"
            autoComplete="off"
            required={!existing}
            className="input font-mono"
            placeholder={existing ? "Leave empty to keep the saved key" : "Paste the Odoo API key"}
          />
          <p className="mt-1 text-xs text-genie-muted">In Odoo: your avatar → Preferences → Account Security → New API Key.</p>
        </div>
        {/* Odoo Online (<name>.odoo.com) needs no database name; only self-hosted Odoo asks for it. */}
        {needsDb && (
          <div>
            <label htmlFor="db" className="label">Database name</label>
            <input id="db" name="db" required className="input" placeholder="yourcompany" defaultValue={existing?.db} />
            <p className="mt-1 text-xs text-genie-muted">Your own Odoo server can hold several databases — ask your Odoo administrator which one.</p>
          </div>
        )}
        <div>
          <label htmlFor="name" className="label">Name in Genie</label>
          <input id="name" name="name" className="input" defaultValue={existing?.name ?? "Odoo"} />
        </div>
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-genie-muted">Using Odoo 18 or older?</summary>
        <div className="mt-2 max-w-md">
          <label htmlFor="login" className="label">Login email of the Odoo user</label>
          <input id="login" name="login" type="email" className="input" placeholder="integration@yourcompany.com" defaultValue={existing?.login} />
          <p className="mt-1 text-xs text-genie-muted">Older Odoo versions need the login together with the API key. Leave empty for Odoo 19 or newer.</p>
        </div>
      </details>
      <details className="text-sm">
        <summary className="cursor-pointer text-genie-muted">Other Odoo data (optional)</summary>
        <p className="mt-2 text-xs text-genie-muted">
          {BRAND.name}{" "}reads contacts, CRM leads and listings by itself. To add other Odoo data, list Odoo&apos;s internal
          names, separated by commas — e.g. <span className="font-mono">sale.order, product.template</span> (Settings →
          Technical → Models in Odoo).
        </p>
        <input id="extra_models" name="extra_models" className="input mt-1 font-mono" placeholder="sale.order, product.template" aria-label="Other Odoo data" defaultValue={existing?.extraModels} />
      </details>
      <button type="submit" className="btn" disabled={pending}>
        {pending ? "Checking with Odoo and saving…" : "Save"}
      </button>
      <p className="text-xs text-genie-muted">Genie checks the address and key with Odoo first. It can then read whatever that Odoo user may see — live, nothing copied.</p>
      {!stale && <FormMessage state={state} />}
    </form>
  );
}

// Visual on/off switch (a button: turning on opens the form, turning off asks to confirm).
export function Switch({ on, onClick, label, disabled }: { on: boolean; onClick?: () => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-50 ${
        on ? "bg-genie-green" : "bg-genie-border"
      }`}
    >
      <span className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform ${on ? "translate-x-5" : "translate-x-0.5"}`} />
    </button>
  );
}

// Odoo when off: the switch opens the connection form.
export function OdooOff({ slug, intro }: { slug: string; intro: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-medium">Odoo</h3>
          <p className="text-sm text-genie-muted">Off — Genie can&apos;t see your Odoo.</p>
        </div>
        <Switch on={open} onClick={() => setOpen(!open)} label="Turn Odoo on" />
      </div>
      {open && (
        <div className="space-y-3 border-t border-genie-border pt-4">
          {intro}
          <OdooForm slug={slug} />
        </div>
      )}
    </div>
  );
}

export type SearchDefaults = { endpoint: string; index: string; name: string; semantic: string; vectorField: string };

export function SearchForm({ slug, d, sourceId }: { slug: string; d: SearchDefaults; sourceId?: string }) {
  const [state, action, pending] = useActionState(connectSearch, undefined);
  const [stale, setStale] = useState(false);
  return (
    <form
      className="space-y-3"
      onChange={() => setStale(true)}
      onSubmit={(e) => {
        e.preventDefault();
        const data = new FormData(e.currentTarget);
        setStale(false);
        startTransition(() => action(data));
      }}
    >
      <input type="hidden" name="slug" value={slug} />
      {sourceId && <input type="hidden" name="source_id" value={sourceId} />}
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="endpoint" className="label">Search service address</label>
          <input id="endpoint" name="endpoint" required className="input" defaultValue={d.endpoint} placeholder="https://yourservice.search.windows.net" />
        </div>
        <div>
          <label htmlFor="index" className="label">Index name</label>
          <input id="index" name="index" required className="input" defaultValue={d.index} placeholder="documents-index" />
        </div>
        <div>
          <label htmlFor="query_key" className="label">Query key</label>
          <input
            id="query_key"
            name="query_key"
            type="password"
            autoComplete="off"
            required={!sourceId}
            className="input font-mono"
            placeholder={sourceId ? "Leave empty to keep the saved key" : "Paste the query key"}
          />
          <p className="mt-1 text-xs text-genie-muted">Azure portal → your search service → Keys → Manage query keys. A query key can only search, never change anything.</p>
        </div>
        <div>
          <label htmlFor="sname" className="label">Name in Genie</label>
          <input id="sname" name="name" className="input" defaultValue={d.name} />
        </div>
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-genie-muted">Search settings (advanced)</summary>
        <div className="mt-2 grid gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor="semantic" className="label">Semantic configuration</label>
            <input id="semantic" name="semantic" className="input font-mono" defaultValue={d.semantic} />
            <p className="mt-1 text-xs text-genie-muted">Ranks results by meaning. Leave empty if the index has none.</p>
          </div>
          <div>
            <label htmlFor="vector_field" className="label">Vector field</label>
            <input id="vector_field" name="vector_field" className="input font-mono" defaultValue={d.vectorField} />
            <p className="mt-1 text-xs text-genie-muted">Used when the index can turn questions into vectors itself; otherwise ignored.</p>
          </div>
        </div>
      </details>
      <button type="submit" className="btn" disabled={pending}>
        {pending ? "Checking the index and saving…" : "Save"}
      </button>
      {!stale && <FormMessage state={state} />}
    </form>
  );
}

// Search index when off: the switch opens the form.
export function SearchOff({ slug, defaults, intro }: { slug: string; defaults: SearchDefaults; intro: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-medium">Document search index</h3>
          <p className="text-sm text-genie-muted">Off — Genie can&apos;t search your documents.</p>
        </div>
        <Switch on={open} onClick={() => setOpen(!open)} label="Turn the search index on" />
      </div>
      {open && (
        <div className="space-y-3 border-t border-genie-border pt-4">
          {intro}
          <SearchForm slug={slug} d={defaults} />
        </div>
      )}
    </div>
  );
}

// A source when on: the switch asks once, then turns it off (forgets the address and key).
export function OffSwitch({ slug, sourceId }: { slug: string; sourceId: string }) {
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);
  if (!confirming) return <Switch on onClick={() => setConfirming(true)} label="Turn off" />;
  return (
    <form
      action={async (data) => {
        setPending(true);
        await removeSource(data);
      }}
      className="flex items-center gap-2 text-sm"
    >
      <input type="hidden" name="slug" value={slug} />
      <input type="hidden" name="source_id" value={sourceId} />
      <span className="text-genie-muted">Turn off and forget the key?</span>
      <button type="submit" disabled={pending} className="btn-secondary px-3 py-1 text-genie-danger">
        {pending ? "Turning off…" : "Turn off"}
      </button>
      <button type="button" onClick={() => setConfirming(false)} className="text-genie-muted underline underline-offset-2">
        Cancel
      </button>
    </form>
  );
}

// "Test connection" on a switched-on source: success or failure, with what was found.
export function TestConnection({ slug, sourceId }: { slug: string; sourceId: string }) {
  const [state, action, pending] = useActionState(testSource, undefined);
  return (
    <form action={action} className="flex flex-wrap items-center justify-end gap-3">
      <input type="hidden" name="slug" value={slug} />
      <input type="hidden" name="source_id" value={sourceId} />
      {state?.ok && <span className="text-sm text-genie-green">{state.ok}</span>}
      {state?.error && <span className="text-sm text-genie-danger">{state.error}</span>}
      <button
        type="submit"
        disabled={pending}
        className="inline-flex items-center justify-center rounded-md bg-blue-50 px-3 py-1.5 text-sm font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-50"
      >
        {pending ? "Testing…" : "Test connection"}
      </button>
    </form>
  );
}

// A switched-on source's box body: details with Edit + Test connection at the bottom right, or the
// form (filled in) while editing.
export function EditableSource({ view, form, test }: { view: React.ReactNode; form: React.ReactNode; test: React.ReactNode }) {
  const [editing, setEditing] = useState(false);
  if (editing) {
    return (
      <div className="space-y-3 border-t border-genie-border pt-4">
        {form}
        <div className="flex justify-end">
          <button type="button" className="btn-secondary" onClick={() => setEditing(false)}>
            Close
          </button>
        </div>
      </div>
    );
  }
  return (
    <>
      {view}
      <div className="flex flex-wrap items-center justify-end gap-2">
        <button type="button" className="btn-secondary" onClick={() => setEditing(true)}>
          Edit
        </button>
        {test}
      </div>
    </>
  );
}
