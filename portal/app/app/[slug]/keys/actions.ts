"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import type { FormState } from "@/components/form-message";
import { type AiModelSettings, BYOK_ORDER, type RouteProvider, validModelId } from "@/lib/ai/models";
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

// Settings → AI model keys → "Model for Ask": the model per provider route, kept in
// tenants.settings.ai_models (owners/admins may update their workspace's settings).
export async function saveModel(_prev: FormState, formData: FormData): Promise<FormState> {
  const slug = String(formData.get("slug"));
  const { supabase, workspace } = await context(slug);
  if (!canManage(workspace.role)) return { error: "Only owners and admins can change the model." };
  const provider = String(formData.get("provider")) as RouteProvider;
  if (!BYOK_ORDER.includes(provider)) return { error: "Unknown provider." };
  const picked = String(formData.get("model") ?? "");
  const model = (picked === "custom" ? String(formData.get("custom_model") ?? "") : picked).trim();
  if (!validModelId(model)) return { error: "Choose a model, or type a model id (letters, digits, . - _ / : only)." };

  const { data: row } = await supabase.from("tenants").select("settings").eq("id", workspace.id).single<{ settings: Record<string, unknown> | null }>();
  const settings = row?.settings ?? {};
  const aiModels = { ...((settings.ai_models as AiModelSettings | undefined) ?? {}), [provider]: model };
  const { error } = await supabase.from("tenants").update({ settings: { ...settings, ai_models: aiModels } }).eq("id", workspace.id);
  if (error) return { error: `Could not save: ${error.message}` };
  revalidatePath(`/app/${slug}`, "layout");
  return { ok: `Saved — Ask now uses ${model}.` };
}
