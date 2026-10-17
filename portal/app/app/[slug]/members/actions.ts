"use server";

import { createHash, randomBytes } from "node:crypto";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import type { FormState } from "@/components/form-message";
import { SITE_URL } from "@/lib/env";
import { getUser } from "@/lib/supabase/server";
import { type Role, canManage, getWorkspace } from "@/lib/workspaces";

const ROLES: Role[] = ["owner", "admin", "member", "viewer"];

async function context(slug: string) {
  const { supabase, user } = await getUser();
  if (!user) redirect("/login");
  const workspace = await getWorkspace(user.id, slug);
  if (!workspace) redirect("/app");
  return { supabase, user, workspace };
}

export type InviteState = { error?: string; ok?: string; link?: string } | undefined;

export async function inviteMember(_prev: InviteState, formData: FormData): Promise<InviteState> {
  const slug = String(formData.get("slug"));
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const role = String(formData.get("role")) as Role;
  const { supabase, user, workspace } = await context(slug);

  if (!canManage(workspace.role)) return { error: "Only owners and admins can invite people." };
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return { error: "Enter a valid email address." };
  if (!["admin", "member", "viewer"].includes(role)) return { error: "Choose a role." };

  // The raw token only ever exists in the link; the database stores its SHA-256.
  const token = randomBytes(24).toString("base64url");
  const tokenHash = createHash("sha256").update(token).digest("hex");
  const { error } = await supabase.from("invitations").insert({
    tenant_id: workspace.id,
    email,
    role,
    token_hash: tokenHash,
    invited_by: user.id,
  });
  if (error) return { error: `Could not create the invitation: ${error.message}` };

  revalidatePath(`/app/${slug}/members`);
  return {
    ok: `Invitation for ${email} created. Send them this link — it works once, for 7 days, only for that email. They can create a password on the link, or use Microsoft or Google.`,
    link: `${SITE_URL}/invite/${token}`,
  };
}

export async function revokeInvitation(formData: FormData) {
  const slug = String(formData.get("slug"));
  const { supabase, workspace } = await context(slug);
  await supabase.from("invitations").delete().eq("id", String(formData.get("id"))).eq("tenant_id", workspace.id);
  revalidatePath(`/app/${slug}/members`);
}

export async function changeRole(_prev: FormState, formData: FormData): Promise<FormState> {
  const slug = String(formData.get("slug"));
  const userId = String(formData.get("user_id"));
  const role = String(formData.get("role")) as Role;
  if (!ROLES.includes(role)) return { error: "Unknown role." };
  const { supabase, workspace } = await context(slug);

  const { data, error } = await supabase
    .from("tenant_members")
    .update({ role })
    .eq("tenant_id", workspace.id)
    .eq("user_id", userId)
    .select("user_id");
  if (error) return { error: error.message };
  if (!data?.length) return { error: "You don't have permission to change this person's role." };
  revalidatePath(`/app/${slug}`, "layout");
  return { ok: "Saved." };
}

export async function removeMember(_prev: FormState, formData: FormData): Promise<FormState> {
  const slug = String(formData.get("slug"));
  const userId = String(formData.get("user_id"));
  const { supabase, user, workspace } = await context(slug);

  const { data, error } = await supabase
    .from("tenant_members")
    .delete()
    .eq("tenant_id", workspace.id)
    .eq("user_id", userId)
    .select("user_id");
  if (error) return { error: error.message };
  if (!data?.length) return { error: "You don't have permission to remove this person." };
  if (userId === user.id) redirect("/app");
  revalidatePath(`/app/${slug}/members`);
  return { ok: "Removed." };
}
