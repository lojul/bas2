"use server";

import { redirect } from "next/navigation";
import type { FormState } from "@/components/form-message";
import { createClient } from "@/lib/supabase/server";

export async function acceptInvitation(_prev: FormState, formData: FormData): Promise<FormState> {
  const token = String(formData.get("token") ?? "");
  const supabase = await createClient();
  const { data: tenantId, error } = await supabase.rpc("accept_invitation", { p_token: token });
  if (error || !tenantId) {
    return { error: "This invitation has expired, was already used, or was sent to a different email address." };
  }
  const { data } = await supabase.from("tenants").select("slug").eq("id", tenantId).single();
  redirect(data ? `/app/${data.slug}` : "/app");
}
