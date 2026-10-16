"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/browser";

const MIN_PASSWORD = 8;

export function NewPasswordForm() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(form: FormData) {
    const password = String(form.get("password") ?? "");
    const confirm = String(form.get("confirm") ?? "");
    setError(null);
    if (password.length < MIN_PASSWORD) return setError(`Use at least ${MIN_PASSWORD} characters.`);
    if (password !== confirm) return setError("The two passwords don't match.");

    setBusy(true);
    const { error } = await createClient().auth.updateUser({ password });
    if (error) {
      setBusy(false);
      setError(
        error.code === "same_password"
          ? "Choose a password different from your current one."
          : error.code === "weak_password"
            ? `Choose a stronger password (at least ${MIN_PASSWORD} characters).`
            : error.message,
      );
      return;
    }
    window.location.assign("/app");
  }

  return (
    <form action={save} className="space-y-3">
      <div>
        <label htmlFor="password" className="label">New password</label>
        <input id="password" name="password" type="password" required minLength={MIN_PASSWORD} autoComplete="new-password" className="input" />
      </div>
      <div>
        <label htmlFor="confirm" className="label">Repeat new password</label>
        <input id="confirm" name="confirm" type="password" required minLength={MIN_PASSWORD} autoComplete="new-password" className="input" />
      </div>
      <button type="submit" disabled={busy} className="btn w-full">
        {busy ? "Saving…" : "Save password and continue"}
      </button>
      {error && <p className="text-sm text-genie-danger">{error}</p>}
    </form>
  );
}
