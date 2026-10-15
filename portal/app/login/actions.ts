"use server";

import type { FormState } from "@/components/form-message";
import { SITE_URL, safeNextPath } from "@/lib/env";
import { createImplicitClient } from "@/lib/supabase/implicit";

export async function sendSignInLink(_prev: FormState, formData: FormData): Promise<FormState> {
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const next = safeNextPath(String(formData.get("next") ?? ""));
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return { error: "Enter a valid email address." };

  const supabase = createImplicitClient();
  const { error } = await supabase.auth.signInWithOtp({
    email,
    options: {
      emailRedirectTo: `${SITE_URL}/auth/confirm?next=${encodeURIComponent(next)}`,
      shouldCreateUser: true,
    },
  });
  if (error) {
    if (error.status === 429) return { error: "Too many sign-in emails were sent. Wait a few minutes and try again." };
    return { error: `Could not send the sign-in email: ${error.message}` };
  }
  return { ok: `Check ${email} — we sent you a sign-in link. Open it to sign in.` };
}
