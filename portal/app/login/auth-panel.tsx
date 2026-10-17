"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/browser";

type Mode = "signin" | "signup" | "forgot";
type Provider = "google" | "azure";
type Message = { kind: "error" | "ok"; text: string } | null;

const MIN_PASSWORD = 8;

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34.1 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34.1 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
    </svg>
  );
}

function MicrosoftIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 21 21" aria-hidden="true">
      <path fill="#F25022" d="M1 1h9v9H1z" />
      <path fill="#7FBA00" d="M11 1h9v9h-9z" />
      <path fill="#00A4EF" d="M1 11h9v9H1z" />
      <path fill="#FFB900" d="M11 11h9v9h-9z" />
    </svg>
  );
}

const PROVIDER_NAME: Record<Provider, string> = { google: "Google", azure: "Microsoft" };

// Plain-English versions of Supabase's sign-in errors.
function explain(code: string | undefined, fallback: string): string {
  switch (code) {
    case "invalid_credentials":
      return "Wrong email or password.";
    case "email_not_confirmed":
      return "Confirm your email address first — check your inbox for the confirmation email.";
    case "user_already_exists":
    case "email_exists":
      return "An account with this email already exists. Sign in instead.";
    case "weak_password":
      return `Choose a stronger password (at least ${MIN_PASSWORD} characters).`;
    case "over_email_send_rate_limit":
    case "over_request_rate_limit":
      return "Too many attempts. Wait a few minutes and try again.";
    case "signup_disabled":
      return "New accounts can't be created right now.";
    default:
      return fallback;
  }
}

export function AuthPanel({
  next,
  google,
  microsoft,
  comingSoon = false,
  autoconfirm,
}: {
  next: string;
  google: boolean;
  microsoft: boolean;
  comingSoon?: boolean;
  autoconfirm: boolean;
}) {
  const [mode, setMode] = useState<Mode>("signin");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<Message>(null);

  const confirmUrl = () => `${window.location.origin}/auth/confirm?next=${encodeURIComponent(next)}`;

  async function withProvider(provider: Provider) {
    setBusy(true);
    setMessage(null);
    const { error } = await createClient().auth.signInWithOAuth({
      provider,
      // Microsoft only returns the email address when asked for it.
      options: { redirectTo: confirmUrl(), scopes: provider === "azure" ? "email" : undefined },
    });
    // On success the browser is already on its way to Google or Microsoft.
    if (error) {
      setBusy(false);
      setMessage({ kind: "error", text: explain(error.code, `${PROVIDER_NAME[provider]} sign-in failed: ${error.message}`) });
    }
  }

  // Emails a link that signs the user in and opens /reset-password to choose a new password.
  async function sendReset(form: FormData) {
    const email = String(form.get("email") ?? "").trim().toLowerCase();
    setMessage(null);
    setBusy(true);
    const { error } = await createClient().auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/auth/confirm?next=${encodeURIComponent("/reset-password")}`,
    });
    setBusy(false);
    if (error) {
      setMessage({ kind: "error", text: explain(error.code, error.message) });
      return;
    }
    // Same answer whether or not the address has an account, so the form can't be used to find accounts.
    setMessage({ kind: "ok", text: `If ${email} has an account, a link to reset the password is on its way. Check your inbox.` });
  }

  async function withPassword(form: FormData) {
    const email = String(form.get("email") ?? "").trim().toLowerCase();
    const password = String(form.get("password") ?? "");
    setMessage(null);
    if (mode === "signup" && password.length < MIN_PASSWORD) {
      setMessage({ kind: "error", text: `Use at least ${MIN_PASSWORD} characters for your password.` });
      return;
    }
    setBusy(true);
    const supabase = createClient();

    if (mode === "signin") {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) {
        setBusy(false);
        setMessage({ kind: "error", text: explain(error.code, error.message) });
        return;
      }
      window.location.assign(next);
      return;
    }

    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: { emailRedirectTo: confirmUrl() },
    });
    setBusy(false);
    if (error) {
      setMessage({ kind: "error", text: explain(error.code, error.message) });
      return;
    }
    if (data.session) {
      window.location.assign(next);
      return;
    }
    // Supabase returns no identities when the email is already registered (it hides this on purpose).
    if (data.user && data.user.identities?.length === 0) {
      setMessage({ kind: "error", text: explain("user_already_exists", "") });
      return;
    }
    setMessage({ kind: "ok", text: `Almost done — open the confirmation email sent to ${email}, then sign in.` });
  }

  return (
    <div>
      {(google || microsoft) && mode !== "forgot" && (
        <>
          <div className="space-y-2">
            {google && (
              <button type="button" onClick={() => withProvider("google")} disabled={busy} className="btn-secondary w-full">
                <GoogleIcon /> Continue with Google
              </button>
            )}
            {microsoft && (
              <button type="button" onClick={() => withProvider("azure")} disabled={busy} className="btn-secondary w-full">
                <MicrosoftIcon /> Continue with Microsoft
              </button>
            )}
          </div>
          <div className="my-5 flex items-center gap-3 text-xs text-genie-muted">
            <span className="h-px flex-1 bg-genie-border" /> or with email <span className="h-px flex-1 bg-genie-border" />
          </div>
        </>
      )}

      {mode === "forgot" ? (
        <form action={sendReset} className="space-y-3">
          <p className="text-sm text-genie-muted">Enter your email and we&apos;ll send you a link to choose a new password.</p>
          <div>
            <label htmlFor="email" className="label">Work email</label>
            <input id="email" name="email" type="email" autoComplete="email" required className="input" placeholder="you@company.com" />
          </div>
          <button type="submit" disabled={busy} className="btn w-full">
            {busy ? "Please wait…" : "Send reset link"}
          </button>
        </form>
      ) : (
        <>
          <div className="mb-4 grid grid-cols-2 rounded-lg border border-genie-border p-1 text-sm">
            {(["signin", "signup"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => {
                  setMode(m);
                  setMessage(null);
                }}
                className={`rounded-md py-1.5 ${mode === m ? "bg-genie-green-deep text-white" : "text-genie-muted hover:text-genie-ink"}`}
              >
                {m === "signin" ? "Sign in" : "Create account"}
              </button>
            ))}
          </div>
    
          <form action={withPassword} className="space-y-3">
            <div>
              <label htmlFor="email" className="label">Work email</label>
              <input id="email" name="email" type="email" autoComplete="email" required className="input" placeholder="you@company.com" />
            </div>
            <div>
              <label htmlFor="password" className="label">Password</label>
              <input
                id="password"
                name="password"
                type="password"
                required
                minLength={mode === "signup" ? MIN_PASSWORD : undefined}
                autoComplete={mode === "signin" ? "current-password" : "new-password"}
                className="input"
              />
              {mode === "signup" && (
                <p className="mt-1 text-xs text-genie-muted">
                  At least {MIN_PASSWORD} characters.{autoconfirm ? "" : " We'll email you a link to confirm your address."}
                </p>
              )}
            </div>
            <button type="submit" disabled={busy} className="btn w-full">
              {busy ? "Please wait…" : mode === "signin" ? "Sign in" : "Create account"}
            </button>
          </form>
        </>
      )}

      {message && (
        <p className={`mt-3 text-sm ${message.kind === "error" ? "text-genie-danger" : "text-genie-green-deep"}`}>{message.text}</p>
      )}
      {mode !== "signup" && (
        <button
          type="button"
          onClick={() => {
            setMode(mode === "forgot" ? "signin" : "forgot");
            setMessage(null);
          }}
          className="mt-3 text-xs text-genie-muted underline underline-offset-2 hover:text-genie-ink"
        >
          {mode === "forgot" ? "Back to sign in" : "Forgot your password?"}
        </button>
      )}
      {comingSoon && mode !== "forgot" && (
        <div className="mt-5 border-t border-genie-border pt-4">
          <p className="mb-2 text-xs text-genie-muted">Coming soon</p>
          <div className="grid grid-cols-2 gap-2">
            <button type="button" disabled className="btn-secondary w-full cursor-not-allowed opacity-50" title="Coming soon">
              <GoogleIcon /> Google
            </button>
            <button type="button" disabled className="btn-secondary w-full cursor-not-allowed opacity-50" title="Coming soon">
              <MicrosoftIcon /> Microsoft
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
