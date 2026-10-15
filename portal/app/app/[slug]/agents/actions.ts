"use server";

import { createHash, randomBytes } from "node:crypto";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { getUser } from "@/lib/supabase/server";
import { canManage, getWorkspace } from "@/lib/workspaces";

export type KeyState = { error?: string; key?: string; name?: string } | undefined;

async function context(slug: string) {
  const { supabase, user } = await getUser();
  if (!user) redirect("/login");
  const workspace = await getWorkspace(user.id, slug);
  if (!workspace) redirect("/app");
  return { supabase, user, workspace };
}

export async function createApiKey(_prev: KeyState, formData: FormData): Promise<KeyState> {
  const slug = String(formData.get("slug"));
  const name = String(formData.get("name") ?? "").trim();
  const { supabase, user, workspace } = await context(slug);
  if (!canManage(workspace.role)) return { error: "Only owners and admins can create API keys." };
  if (!name || name.length > 100) return { error: "Give the key a name, e.g. “Claude Desktop – Kin”." };

  // Shown once; only its SHA-256 is stored.
  const key = `gnk_${randomBytes(32).toString("base64url")}`;
  const { error } = await supabase.from("api_keys").insert({
    tenant_id: workspace.id,
    name,
    prefix: key.slice(0, 12),
    key_hash: createHash("sha256").update(key).digest("hex"),
    created_by: user.id,
  });
  if (error) return { error: `Could not create the key: ${error.message}` };
  revalidatePath(`/app/${slug}/settings`);
  return { key, name };
}

export async function revokeApiKey(formData: FormData) {
  const slug = String(formData.get("slug"));
  const { supabase, workspace } = await context(slug);
  await supabase
    .from("api_keys")
    .update({ revoked_at: new Date().toISOString() })
    .eq("id", String(formData.get("id")))
    .eq("tenant_id", workspace.id);
  revalidatePath(`/app/${slug}/settings`);
}
