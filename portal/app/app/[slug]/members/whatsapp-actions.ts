"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { getUser } from "@/lib/supabase/server";
import { startLink, unlink } from "@/lib/whatsapp/links";
import { getWorkspace } from "@/lib/workspaces";

// Members → Your WhatsApp: every member links (and unlinks) their own number.
async function context(slug: string) {
  const { user } = await getUser();
  if (!user) redirect("/login");
  const workspace = await getWorkspace(user.id, slug);
  if (!workspace) redirect("/app");
  return { user, workspace };
}

export type LinkState = { error?: string; code?: string; expiresAt?: string } | undefined;

export async function startWhatsAppLink(_prev: LinkState, formData: FormData): Promise<LinkState> {
  const slug = String(formData.get("slug"));
  const { user, workspace } = await context(slug);
  try {
    return await startLink(workspace.id, user.id);
  } catch (e) {
    return { error: `Could not make a code: ${e instanceof Error ? e.message : e}` };
  }
}

export async function unlinkWhatsApp(formData: FormData) {
  const slug = String(formData.get("slug"));
  const { user, workspace } = await context(slug);
  await unlink(workspace.id, user.id);
  revalidatePath(`/app/${slug}/members`);
}
