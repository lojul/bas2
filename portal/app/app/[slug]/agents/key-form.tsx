"use client";

import { useActionState, useState } from "react";
import { Check, Copy } from "lucide-react";
import { SubmitButton } from "@/components/submit-button";
import { createApiKey } from "./actions";

function CopyField({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div>
      <div className="mb-1 text-xs font-medium text-genie-muted">{label}</div>
      <div className="flex items-start gap-2">
        <pre className="input min-w-0 flex-1 overflow-x-auto whitespace-pre font-mono text-xs">{value}</pre>
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
    </div>
  );
}

export function KeyForm({ slug, endpoint }: { slug: string; endpoint: string }) {
  const [state, action] = useActionState(createApiKey, undefined);

  const desktopConfig = state?.key
    ? JSON.stringify(
        {
          mcpServers: {
            genie: {
              command: "npx",
              args: ["-y", "mcp-remote", endpoint, "--header", "Authorization:Bearer ${GENIE_KEY}"],
              env: { GENIE_KEY: state.key },
            },
          },
        },
        null,
        2,
      )
    : "";

  return (
    <div>
      <form action={action} className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <input type="hidden" name="slug" value={slug} />
        <div className="flex-1">
          <label htmlFor="key-name" className="label">Key name</label>
          <input id="key-name" name="name" required maxLength={100} className="input" placeholder="Claude Desktop – Kin" />
        </div>
        <SubmitButton pendingText="Creating…">Create API key</SubmitButton>
      </form>
      {state?.error && <p className="mt-3 text-sm text-genie-danger">{state.error}</p>}
      {state?.key && (
        <div className="mt-5 space-y-4 rounded-lg border border-genie-border bg-genie-bg p-4">
          <p className="text-sm font-medium">
            Key “{state.name}” created. Copy it now — it won&apos;t be shown again.
          </p>
          <CopyField label="API key" value={state.key} />
          <CopyField label="Claude Desktop (claude_desktop_config.json)" value={desktopConfig} />
          <CopyField label="Other MCP clients — Streamable HTTP URL with header Authorization: Bearer <key>" value={endpoint} />
        </div>
      )}
    </div>
  );
}
