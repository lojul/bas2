"use server";

import { redirect } from "next/navigation";
import type { FormState } from "@/components/form-message";
import { findInvitation } from "@/lib/invites";
import { createAdminClient } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

const MIN_PASSWORD = 8;

async function join(token: string): Promise<FormState> {
  const supabase = await createClient();
  const { data: tenantId, error } = await supabase.rpc("accept_invitation", { p_token: token });
  if (error || !tenantId) {
    return { error: "This invitation has expired, was already used, or was sent to a different email address." };
  }
  const { data } = await supabase.from("tenants").select("slug").eq("id", tenantId).single();
  redirect(data ? `/app/${data.slug}` : "/app");
}

export async function acceptInvitation(_prev: FormState, formData: FormData): Promise<FormState> {
  return join(String(formData.get("token") ?? ""));
}

// New person, email + password: the invite link proves the invitation reached them, so the account is
// created already confirmed (Genie can't send confirmation emails yet), then signed in and joined.
export async function createAccountAndJoin(_prev: FormState, formData: FormData): Promise<FormState> {
  const token = String(formData.get("token") ?? "");
  const password = String(formData.get("password") ?? "");
  const repeat = String(formData.get("repeat") ?? "");
  const invite = await findInvitation(token);
  if (!invite || invite.expired || invite.used) return { error: "This invitation has expired or was already used. Ask for a new one." };
  if (password.length < MIN_PASSWORD) return { error: `Use at least ${MIN_PASSWORD} characters.` };
  if (password !== repeat) return { error: "The two passwords don't match." };

  const { error: createError } = await createAdminClient().auth.admin.createUser({ email: invite.email, password, email_confirm: true });
  if (createError) {
    if (/already|exists|registered/i.test(createError.message)) {
      return { error: `There is already an account for ${invite.email}. Sign in instead (link below), then accept.` };
    }
    return { error: `Could not create the account: ${createError.message}` };
  }
  const supabase = await createClient();
  const { error: signInError } = await supabase.auth.signInWithPassword({ email: invite.email, password });
  if (signInError) return { error: `Account created, but signing in failed: ${signInError.message}. Try signing in.` };
  return join(token);
}
