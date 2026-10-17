"use server";

import { createAdminClient } from "@/lib/supabase/admin";
import { getUser } from "@/lib/supabase/server";
import { canManage, getWorkspace } from "@/lib/workspaces";

// Reveals one saved key of a workspace, on request (the 👁 / copy buttons in key fields). Owners and
// admins only; the value is read from Vault at that moment and never put in a page by default.
// Workspace API keys for AI agents (gnk_…) can't be revealed: Genie keeps only their hash.
export async function revealSecret(slug: string, name: string): Promise<{ ok: true; value: string } | { ok: false; error: string }> {
  const { supabase, user } = await getUser();
  if (!user) return { ok: false, error: "Sign in again." };
  const workspace = await getWorkspace(user.id, slug);
  if (!workspace || !canManage(workspace.role)) return { ok: false, error: "Only owners and admins can see saved keys." };
  if (!/^[a-z0-9_.-]{1,64}$/.test(name)) return { ok: false, error: "Unknown key." };

  // The key must belong to this workspace (row-level security limits what the member can see).
  const { data: row } = await supabase.from("tenant_secrets").select("id").eq("tenant_id", workspace.id).eq("name", name).maybeSingle();
  if (!row) return { ok: false, error: "No saved key." };
  const { data, error } = await createAdminClient().rpc("get_tenant_secret", { p_tenant_id: workspace.id, p_name: name });
  if (error || typeof data !== "string") return { ok: false, error: "Could not read the saved key." };
  return { ok: true, value: data };
}
