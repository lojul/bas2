"use client";

import { useState } from "react";
import { Check, Copy, Eye, EyeOff } from "lucide-react";
import { revealSecret } from "@/app/app/[slug]/reveal-action";

// A key field. A saved key shows as dots; 👁 shows it and ⧉ copies it (fetched from Vault only when
// clicked). Typing replaces it; leaving the dots untouched keeps the saved key.
export function SecretInput({
  id,
  name,
  placeholder,
  saved,
  required,
}: {
  id: string;
  name: string;
  placeholder: string;
  saved?: { slug: string; secretName: string } | null;
  required?: boolean;
}) {
  const [value, setValue] = useState("");
  const [shown, setShown] = useState(false);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function current(): Promise<string | null> {
    if (value || !saved) return value || null;
    setBusy(true);
    const res = await revealSecret(saved.slug, saved.secretName);
    setBusy(false);
    if (!res.ok) {
      setError(res.error);
      return null;
    }
    setError(null);
    setValue(res.value);
    return res.value;
  }

  const iconButton = "rounded p-1 text-genie-muted hover:bg-genie-hover hover:text-genie-ink disabled:opacity-40";
  return (
    <div>
      <div className="relative">
        <input
          id={id}
          name={name}
          type={shown ? "text" : "password"}
          autoComplete="off"
          spellCheck={false}
          required={required && !saved}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          // A saved key looks like a filled-in password until it is shown or replaced.
          placeholder={saved ? "••••••••••••••••••••••••" : placeholder}
          className={`input pr-16 font-mono ${saved && !value ? "placeholder:text-genie-ink placeholder:tracking-widest" : ""}`}
        />
        <div className="absolute right-1.5 top-1/2 flex -translate-y-1/2 gap-0.5">
          <button
            type="button"
            className={iconButton}
            disabled={busy || (!saved && !value)}
            title={shown ? "Hide" : "Show"}
            aria-label={shown ? "Hide key" : "Show key"}
            onClick={async () => {
              if (!shown && !(await current())) return;
              setShown(!shown);
            }}
          >
            {shown ? <EyeOff size={15} /> : <Eye size={15} />}
          </button>
          <button
            type="button"
            className={iconButton}
            disabled={busy || (!saved && !value)}
            title="Copy"
            aria-label="Copy key"
            onClick={async () => {
              const v = await current();
              if (!v) return;
              await navigator.clipboard.writeText(v);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}
          >
            {copied ? <Check size={15} /> : <Copy size={15} />}
          </button>
        </div>
      </div>
      {error && <p className="mt-1 text-xs text-genie-danger">{error}</p>}
    </div>
  );
}

// A saved key shown in a list (e.g. AI model keys): dots + last four characters, with show and copy.
export function SecretView({ slug, secretName, hint }: { slug: string; secretName: string; hint: string | null }) {
  const [value, setValue] = useState<string | null>(null);
  const [shown, setShown] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (value) return value;
    const res = await revealSecret(slug, secretName);
    if (!res.ok) {
      setError(res.error);
      return null;
    }
    setValue(res.value);
    return res.value;
  }

  const iconButton = "rounded p-1 text-genie-muted hover:bg-genie-hover hover:text-genie-ink";
  return (
    <span className="inline-flex min-w-0 items-center gap-1">
      <span className="truncate font-mono text-xs text-genie-muted">{shown && value ? value : `••••••••••••${hint ?? ""}`}</span>
      <button
        type="button"
        className={iconButton}
        title={shown ? "Hide" : "Show"}
        aria-label={shown ? "Hide key" : "Show key"}
        onClick={async () => {
          if (!shown && !(await load())) return;
          setShown(!shown);
        }}
      >
        {shown ? <EyeOff size={14} /> : <Eye size={14} />}
      </button>
      <button
        type="button"
        className={iconButton}
        title="Copy"
        aria-label="Copy key"
        onClick={async () => {
          const v = await load();
          if (!v) return;
          await navigator.clipboard.writeText(v);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
      >
        {copied ? <Check size={14} /> : <Copy size={14} />}
      </button>
      {error && <span className="text-xs text-genie-danger">{error}</span>}
    </span>
  );
}
