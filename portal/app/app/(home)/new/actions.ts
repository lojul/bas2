"use server";

import { redirect } from "next/navigation";
import type { FormState } from "@/components/form-message";
import { createClient } from "@/lib/supabase/server";

export async function createWorkspace(_prev: FormState, formData: FormData): Promise<FormState> {
  const name = String(formData.get("name") ?? "").trim();
  const slug = String(formData.get("slug") ?? "").trim().toLowerCase();
  if (!name) return { error: "Enter your company name." };
  if (!/^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$/.test(slug)) {
    return { error: "The web address must be 3–50 characters: lowercase letters, numbers and dashes." };
  }

  const supabase = await createClient();
  const { error } = await supabase.rpc("create_tenant", { p_name: name, p_slug: slug });
  if (error) {
    if (error.code === "23505") return { error: `“${slug}” is already taken. Choose another web address.` };
    return { error: `Could not create the workspace: ${error.message}` };
  }
  redirect(`/app/${slug}`);
}
