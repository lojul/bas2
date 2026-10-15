"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import type { FormState } from "@/components/form-message";
import { AI_PROVIDERS } from "@/lib/providers";
import { getUser } from "@/lib/supabase/server";
import { canManage, getWorkspace } from "@/lib/workspaces";

async function context(slug: string) {
  const { supabase, user } = await getUser();
  if (!user) redirect("/login");
  const workspace = await getWorkspace(user.id, slug);
  if (!workspace) redirect("/app");
  return { supabase, workspace };
}

export async function saveAiKey(_prev: FormState, formData: FormData): Promise<FormState> {
  const slug = String(formData.get("slug"));
  const provider = String(formData.get("provider"));
  const key = String(formData.get("key") ?? "").trim();
  const { supabase, workspace } = await context(slug);

  if (!canManage(workspace.role)) return { error: "Only owners and admins can manage AI keys." };
  if (!AI_PROVIDERS.some((p) => p.id === provider)) return { error: "Choose a provider." };
  if (key.length < 16) return { error: "That doesn't look like a complete API key." };

  // Stored encrypted in Supabase Vault; the database keeps only the last 4 characters for display.
  const { error } = await supabase.rpc("set_tenant_secret", {
    p_tenant_id: workspace.id,
    p_name: `ai_${provider}`,
    p_kind: "ai_key",
    p_provider: provider,
    p_secret: key,
  });
  if (error) return { error: `Could not save the key: ${error.message}` };
  revalidatePath(`/app/${slug}`, "layout");
  return { ok: "Key saved. It is stored encrypted and can't be shown again." };
}

export async function deleteAiKey(formData: FormData) {
  const slug = String(formData.get("slug"));
  const { supabase, workspace } = await context(slug);
  await supabase.rpc("delete_tenant_secret", { p_tenant_id: workspace.id, p_name: String(formData.get("name")) });
  revalidatePath(`/app/${slug}`, "layout");
}
