"use client";

import { startTransition, useActionState, useState } from "react";
import { Check, Copy } from "lucide-react";
import { FormMessage } from "@/components/form-message";
import { SecretInput } from "@/components/secret-input";
import { SLACK_SIGNING_SECRET, SLACK_TOKEN_SECRET } from "@/lib/slack/names";
import { Switch } from "../sources/forms";
import { connectSlack, disconnectSlack, setSlackEnabled, testSlack } from "./actions";

function SlackForm({ slug, editing }: { slug: string; editing: boolean }) {
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
          <SecretInput id="bot_token" name="bot_token" required placeholder="xoxb-…" saved={editing ? { slug, secretName: SLACK_TOKEN_SECRET } : null} />
          <p className="mt-1 text-xs text-genie-muted">api.slack.com/apps → your app → OAuth &amp; Permissions.</p>
        </div>
        <div>
          <label htmlFor="signing_secret" className="label">Signing Secret</label>
          <SecretInput id="signing_secret" name="signing_secret" required placeholder="Paste the signing secret" saved={editing ? { slug, secretName: SLACK_SIGNING_SECRET } : null} />
          <p className="mt-1 text-xs text-genie-muted">Same app → Basic Information → App Credentials.</p>
        </div>
      </div>
      <button type="submit" className="btn" disabled={pending}>
        {pending ? "Checking with Slack and saving…" : "Save"}
      </button>
      {!stale && <FormMessage state={state} />}
    </form>
  );
}

export function SlackOff({ slug }: { slug: string }) {
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
          <SlackForm slug={slug} editing={false} />
        </div>
      )}
    </div>
  );
}

// The Slack on/off switch on a connected Slack (keys stay saved).
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
        aria-label={enabled ? "Turn Slack off" : "Turn Slack on"}
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

// Connected Slack: the form filled in (keys masked), then Disconnect and Test connection.
export function SlackActions({ slug }: { slug: string }) {
  const [state, action, pending] = useActionState(testSlack, undefined);
  return (
    <>
      <div className="border-t border-genie-border pt-4">
        <SlackForm slug={slug} editing />
      </div>
      <div className="flex flex-wrap items-center justify-end gap-2">
        <DisconnectSlack slug={slug} />
        <form action={action} className="flex flex-wrap items-center justify-end gap-2">
          <input type="hidden" name="slug" value={slug} />
          {state?.ok && <span className="text-sm text-genie-green">{state.ok}</span>}
          {state?.error && <span className="text-sm text-genie-danger">{state.error}</span>}
          <button type="submit" disabled={pending} className="inline-flex items-center justify-center rounded-md bg-blue-50 px-3 py-1.5 text-sm font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-50">
            {pending ? "Testing…" : "Test connection"}
          </button>
        </form>
      </div>
    </>
  );
}
