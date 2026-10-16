"use client";

import { startTransition, useActionState, useState } from "react";
import { Check, Copy } from "lucide-react";
import { FormMessage } from "@/components/form-message";
import { Switch } from "../sources/forms";
import { connectSlack, disconnectSlack, setSlackEnabled, testSlack } from "./actions";

function SlackForm({ slug, editing, fallback }: { slug: string; editing: boolean; fallback: string }) {
  const [state, action, pending] = useActionState(connectSlack, undefined);
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
      {editing && <input type="hidden" name="editing" value="1" />}
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="bot_token" className="label">Bot User OAuth Token</label>
          <input id="bot_token" name="bot_token" type="password" autoComplete="off" required={!editing} className="input font-mono" placeholder={editing ? "Leave empty to keep the saved token" : "xoxb-…"} />
          <p className="mt-1 text-xs text-genie-muted">api.slack.com/apps → your app → OAuth &amp; Permissions.</p>
        </div>
        <div>
          <label htmlFor="signing_secret" className="label">Signing Secret</label>
          <input id="signing_secret" name="signing_secret" type="password" autoComplete="off" required={!editing} className="input font-mono" placeholder={editing ? "Leave empty to keep the saved secret" : "Paste the signing secret"} />
          <p className="mt-1 text-xs text-genie-muted">Same app → Basic Information → App Credentials.</p>
        </div>
      </div>
      <div>
        <label htmlFor="fallback_url" className="label">When Genie is switched off, pass messages to (optional)</label>
        <input id="fallback_url" name="fallback_url" className="input font-mono text-xs" defaultValue={fallback} placeholder="https://your-old-bot.example.com/api/slack/events" />
        <p className="mt-1 text-xs text-genie-muted">
          The bot&apos;s previous Request URL. With it, the switch below moves Slack between Genie and the old bot — no Slack settings to change.
        </p>
      </div>
      <button type="submit" className="btn" disabled={pending}>
        {pending ? "Checking with Slack and saving…" : "Save"}
      </button>
      {!stale && <FormMessage state={state} />}
    </form>
  );
}

export function SlackOff({ slug, fallback }: { slug: string; fallback: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-medium">Slack</h3>
          <p className="text-sm text-genie-muted">Off — staff can&apos;t ask Genie in Slack yet.</p>
        </div>
        <Switch on={open} onClick={() => setOpen(!open)} label="Turn Slack on" />
      </div>
      {open && (
        <div className="space-y-3 border-t border-genie-border pt-4">
          <p className="text-sm text-genie-muted">
            Use your own Slack app — a new one, or the bot your team already has. Genie keeps only the two keys (encrypted) and reads
            nothing from Slack except the questions asked to it.
          </p>
          <SlackForm slug={slug} editing={false} fallback={fallback} />
        </div>
      )}
    </div>
  );
}

// The switch on a connected Slack: who answers — Genie (on) or the previous bot / nobody (off).
export function SlackEnabledSwitch({ slug, enabled }: { slug: string; enabled: boolean }) {
  const [pending, setPending] = useState(false);
  return (
    <form
      action={async (data) => {
        setPending(true);
        await setSlackEnabled(data);
        setPending(false);
      }}
    >
      <input type="hidden" name="slug" value={slug} />
      <input type="hidden" name="enabled" value={enabled ? "0" : "1"} />
      <button
        type="submit"
        role="switch"
        aria-checked={enabled}
        aria-label={enabled ? "Switch Genie off in Slack" : "Switch Genie on in Slack"}
        disabled={pending}
        className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-50 ${enabled ? "bg-genie-green" : "bg-genie-border"}`}
      >
        <span className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform ${enabled ? "translate-x-5" : "translate-x-0.5"}`} />
      </button>
    </form>
  );
}

function DisconnectSlack({ slug }: { slug: string }) {
  const [confirming, setConfirming] = useState(false);
  if (!confirming) {
    return (
      <button type="button" className="btn-danger mr-auto" onClick={() => setConfirming(true)}>
        Disconnect
      </button>
    );
  }
  return (
    <form action={disconnectSlack} className="mr-auto flex items-center gap-2 text-sm">
      <input type="hidden" name="slug" value={slug} />
      <span className="text-genie-muted">Forget the Slack keys?</span>
      <button type="submit" className="btn-secondary px-3 py-1 text-genie-danger">Disconnect</button>
      <button type="button" onClick={() => setConfirming(false)} className="text-genie-muted underline underline-offset-2">Cancel</button>
    </form>
  );
}

export function CopyField({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-center gap-2">
      <code className="input min-w-0 flex-1 truncate font-mono text-xs">{value}</code>
      <button
        type="button"
        className="btn-secondary shrink-0"
        onClick={async () => {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        }}
      >
        {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

// Edit + Test connection at the bottom right; the form (keys optional) while editing.
export function SlackActions({ slug, fallback }: { slug: string; fallback: string }) {
  const [editing, setEditing] = useState(false);
  const [state, action, pending] = useActionState(testSlack, undefined);
  if (editing) {
    return (
      <div className="space-y-3 border-t border-genie-border pt-4">
        <SlackForm slug={slug} editing fallback={fallback} />
        <div className="flex justify-end">
          <button type="button" className="btn-secondary" onClick={() => setEditing(false)}>Close</button>
        </div>
      </div>
    );
  }
  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <DisconnectSlack slug={slug} />
      <form action={action} className="flex flex-wrap items-center justify-end gap-2">
      <input type="hidden" name="slug" value={slug} />
      {state?.ok && <span className="text-sm text-genie-green">{state.ok}</span>}
      {state?.error && <span className="text-sm text-genie-danger">{state.error}</span>}
      <button type="button" className="btn-secondary" onClick={() => setEditing(true)}>Edit</button>
      <button type="submit" disabled={pending} className="inline-flex items-center justify-center rounded-md bg-blue-50 px-3 py-1.5 text-sm font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-50">
        {pending ? "Testing…" : "Test connection"}
      </button>
      </form>
    </div>
  );
}
