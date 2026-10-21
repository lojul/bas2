"use client";

import { startTransition, useActionState, useState } from "react";
import { FormMessage } from "@/components/form-message";
import { SecretInput } from "@/components/secret-input";
import type { ChangeAction, Who } from "@/lib/odoo/changes";
import { saveOdooChanges, setOdooChangesEnabled, testOdooChanges } from "./changes-actions";
import { Switch } from "./forms";

export type ChangesCardProps = {
  slug: string;
  enabled: boolean;
  keySaved: boolean;
  actions: { id: ChangeAction; label: string; hint: string; on: boolean; who: Who }[];
  dailyLimit: number;
  updateFields: string[];
  fieldChoices: { model: string; label: string; fields: { name: string; label: string }[] }[];
};

// Settings → Data sources → "Changes in Odoo" (user decision 2026-10-17): off by default; every
// change is a draft someone confirms on Ask.
export function OdooChangesCard(p: ChangesCardProps) {
  const [open, setOpen] = useState(p.enabled);
  const [switching, setSwitching] = useState(false);
  const [state, action, pending] = useActionState(saveOdooChanges, undefined);
  const [test, testAction, testing] = useActionState(testOdooChanges, undefined);
  const [stale, setStale] = useState(false);

  async function toggle() {
    if (!p.enabled) {
      setOpen(!open); // switched on by Save, once the key is in
      return;
    }
    setSwitching(true);
    const data = new FormData();
    data.set("slug", p.slug);
    data.set("enabled", "0");
    await setOdooChangesEnabled(data);
    setSwitching(false);
    setOpen(false);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-medium">Changes in Odoo</h3>
          {p.enabled ? (
            <p className="text-sm text-genie-green">On — Genie prepares changes on Ask; nothing is saved until someone presses Confirm</p>
          ) : (
            <p className="text-sm text-genie-muted">Off — Genie only reads Odoo.</p>
          )}
        </div>
        <Switch on={p.enabled || open} onClick={toggle} disabled={switching} label={p.enabled ? "Turn changes in Odoo off" : "Turn changes in Odoo on"} />
      </div>

      {(open || p.enabled) && (
        <form
          className="space-y-5 border-t border-genie-border pt-4"
          onChange={() => setStale(true)}
          onSubmit={(e) => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            setStale(false);
            startTransition(() => action(data));
          }}
        >
          <input type="hidden" name="slug" value={p.slug} />
          <div className="rounded-lg bg-genie-accent/60 p-4 text-sm">
            <p className="font-medium">How it works</p>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-genie-ink/90">
              <li>On Ask, someone writes e.g. &quot;create a lead for Chan Tai Man, 9123 4567, wants a 3-bed in Taikoo Shing&quot;.</li>
              <li>Genie shows a draft with <b>Confirm</b> / <b>Cancel</b>. Only after Confirm does Genie write to Odoo, with the key below.</li>
              <li>Each change is noted on the Odoo record (&quot;Done by Genie at the request of …&quot;) and listed under Settings → Activity.</li>
              <li>Only on Ask (web) for now — on Slack and WhatsApp Genie can&apos;t yet tell which member is asking.</li>
            </ul>
          </div>

          <div className="max-w-xl">
            <label htmlFor="write_key" className="label">API key of the Genie Odoo user</label>
            <SecretInput id="write_key" name="write_key" required={!p.keySaved} placeholder="Paste the API key" saved={p.keySaved ? { slug: p.slug, secretName: "odoo_write_key" } : null} />
            <p className="mt-1 text-xs text-genie-muted">
              In Odoo: Settings → Users → New user &quot;Genie&quot; (internal user; Sales: User — own documents or all, Contacts: Creation). Then log in as
              that user → My Profile → Account Security → New API key, Scope &quot;RPC&quot;. Changes are made with this user&apos;s rights only. Reading still uses the key in the
              Odoo card above.
            </p>
          </div>

          <div>
            <p className="label">What Genie may prepare, and who may ask</p>
            <ul className="divide-y divide-genie-border rounded-lg border border-genie-border">
              {p.actions.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                  <label className="flex items-start gap-3">
                    <input type="checkbox" name={`on_${a.id}`} value="1" defaultChecked={a.on} className="mt-1.5 h-4 w-4 accent-black" />
                    <span>
                      <span className="block text-sm font-medium">{a.label}</span>
                      <span className="block text-xs text-genie-muted">{a.hint}</span>
                    </span>
                  </label>
                  <select name={`who_${a.id}`} defaultValue={a.who} className="input w-auto" aria-label={`Who may ask: ${a.label}`}>
                    <option value="member">Members and admins</option>
                    <option value="admin">Admins only</option>
                  </select>
                </li>
              ))}
            </ul>
            <p className="mt-1 text-xs text-genie-muted">Viewers can never ask for changes.</p>
          </div>

          <div>
            <p className="label">Fields Genie may update (for &quot;Update fields on a record&quot;)</p>
            {p.fieldChoices.length === 0 ? (
              <p className="text-sm text-genie-muted">{p.keySaved ? "The Genie Odoo user can't read any record types yet." : "Save the key first; the fields are then read from Odoo."}</p>
            ) : (
              <div className="space-y-2">
                {p.fieldChoices.map((m) => {
                  const ticked = m.fields.filter((f) => p.updateFields.includes(`${m.model}:${f.name}`)).length;
                  return (
                    <details key={m.model} className="rounded-lg border border-genie-border px-4 py-2.5">
                      <summary className="cursor-pointer text-sm">
                        {m.label} <span className="text-genie-muted">· {ticked ? `${ticked} allowed` : "none allowed"}</span>
                      </summary>
                      <div className="mt-3 grid gap-x-4 gap-y-1.5 sm:grid-cols-2 lg:grid-cols-3">
                        {m.fields.map((f) => (
                          <label key={f.name} className="flex items-center gap-2 text-sm" title={f.name}>
                            <input
                              type="checkbox"
                              name="update_fields"
                              value={`${m.model}:${f.name}`}
                              defaultChecked={p.updateFields.includes(`${m.model}:${f.name}`)}
                              className="h-4 w-4 accent-black"
                            />
                            <span className="truncate">{f.label}</span>
                          </label>
                        ))}
                      </div>
                    </details>
                  );
                })}
              </div>
            )}
          </div>

          <div className="max-w-48">
            <label htmlFor="daily_limit" className="label">Most changes per day</label>
            <input id="daily_limit" name="daily_limit" type="number" min={1} max={1000} defaultValue={p.dailyLimit} className="input" />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <button type="submit" className="btn" disabled={pending}>
              {pending ? "Checking the key and saving…" : "Save"}
            </button>
          </div>
          {!stale && <FormMessage state={state} />}
        </form>
      )}

      {p.keySaved && (
        <form action={testAction} className="flex flex-wrap items-center justify-end gap-2">
          <input type="hidden" name="slug" value={p.slug} />
          {test?.ok && <span className="text-sm text-genie-green">{test.ok}</span>}
          {test?.error && <span className="text-sm text-genie-danger">{test.error}</span>}
          <button type="submit" disabled={testing} className="inline-flex items-center justify-center rounded-md bg-blue-50 px-4 py-2 text-sm font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-50">
            {testing ? "Testing…" : "Test connection"}
          </button>
        </form>
      )}
    </div>
  );
}
