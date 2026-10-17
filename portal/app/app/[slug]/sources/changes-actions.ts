"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import type { FormState } from "@/components/form-message";
import { CHANGE_ACTIONS, type ChangeSettings, describeWriteUser, ODOO_WRITE_SECRET, type Who } from "@/lib/odoo/changes";
import { getUser } from "@/lib/supabase/server";
import { canManage, getWorkspace } from "@/lib/workspaces";

// Settings → Data sources → "Changes in Odoo" (owners/admins).
async function context(slug: string) {
  const { supabase, user } = await getUser();
  if (!user) redirect("/login");
  const workspace = await getWorkspace(user.id, slug);
  if (!workspace) redirect("/app");
  if (!canManage(workspace.role)) throw new Error("Only owners and admins can change this.");
  const { data } = await supabase.from("tenants").select("settings").eq("id", workspace.id).single<{ settings: Record<string, unknown> | null }>();
  const settings = data?.settings ?? {};
  const save = async (odoo_changes: ChangeSettings) => {
    const { error } = await supabase.from("tenants").update({ settings: { ...settings, odoo_changes } }).eq("id", workspace.id);
    if (error) throw new Error(error.message);
  };
  return { supabase, workspace, current: (settings.odoo_changes as ChangeSettings | undefined) ?? {}, save };
}

export async function setOdooChangesEnabled(formData: FormData) {
  const slug = String(formData.get("slug"));
  const { current, save } = await context(slug);
  await save({ ...current, enabled: formData.get("enabled") === "1" });
  revalidatePath(`/app/${slug}/settings`);
}

export async function saveOdooChanges(_prev: FormState, formData: FormData): Promise<FormState> {
  const slug = String(formData.get("slug"));
  try {
    const { supabase, workspace, current, save } = await context(slug);
    const key = String(formData.get("write_key") ?? "").trim();
    if (key) {
      // Check the key before keeping it.
      await describeWriteUser(workspace.id, key).catch((e) => {
        throw new Error(`Odoo refused this key: ${e instanceof Error ? e.message : e}`);
      });
      const { error } = await supabase.rpc("set_tenant_secret", { p_tenant_id: workspace.id, p_name: ODOO_WRITE_SECRET, p_kind: "connector", p_provider: "odoo", p_secret: key });
      if (error) return { error: `Could not save the key: ${error.message}` };
    }
    const actions: ChangeSettings["actions"] = {};
    for (const a of CHANGE_ACTIONS) {
      actions[a.id] = { on: formData.get(`on_${a.id}`) === "1", who: (formData.get(`who_${a.id}`) === "admin" ? "admin" : "member") as Who };
    }
    const limit = Math.min(Math.max(Math.round(Number(formData.get("daily_limit")) || 50), 1), 1000);
    const fields = formData.getAll("update_fields").map(String).filter((f) => /^[\w.]+:\w+$/.test(f)).slice(0, 200);
    await save({ ...current, enabled: true, actions, daily_limit: limit, update_fields: fields });
    revalidatePath(`/app/${slug}/settings`);
    return { ok: "Saved. Members can now ask Genie on Ask to prepare these changes; each one waits for Confirm." };
  } catch (e) {
    return { error: e instanceof Error ? e.message : String(e) };
  }
}

export async function testOdooChanges(_prev: FormState, formData: FormData): Promise<FormState> {
  const slug = String(formData.get("slug"));
  try {
    const { workspace } = await context(slug);
    const who = await describeWriteUser(workspace.id);
    const leads = who.canCreateLeads === null ? "" : who.canCreateLeads ? " · may create leads" : " · may NOT create leads (check its Odoo rights)";
    return who.canCreateLeads === false ? { error: `Connected as ${who.name} (${who.login})${leads}` } : { ok: `✓ Connected as ${who.name} (${who.login})${leads}` };
  } catch (e) {
    return { error: `✗ ${e instanceof Error ? e.message : String(e)}` };
  }
}
