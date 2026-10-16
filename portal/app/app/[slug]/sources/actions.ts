"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import type { FormState } from "@/components/form-message";
import { createAdminClient } from "@/lib/supabase/admin";
import { getUser } from "@/lib/supabase/server";
import { OdooClient, OdooError, normaliseUrl } from "@/lib/sync/odoo";
import { DEFAULT_ODOO_MODELS, guessOdooDb } from "@/lib/sync/models";
import { syncOdoo } from "@/lib/sync/odoo-sync";
import { canManage, getWorkspace } from "@/lib/workspaces";

async function context(slug: string) {
  const { supabase, user } = await getUser();
  if (!user) redirect("/login");
  const workspace = await getWorkspace(user.id, slug);
  if (!workspace) redirect("/app");
  if (!canManage(workspace.role)) throw new Error("Only owners and admins can manage data sources.");
  return { supabase, user, workspace };
}

const parseModels = (raw: string) =>
  [...new Set(raw.split(/[\s,]+/).map((m) => m.trim()).filter((m) => /^[a-z][a-z0-9_.]*$/.test(m)))].slice(0, 20);

export async function connectOdoo(_prev: FormState, formData: FormData): Promise<FormState> {
  const slug = String(formData.get("slug"));
  const { supabase, user, workspace } = await context(slug);
  const name = String(formData.get("name") ?? "").trim() || "Odoo";
  const login = String(formData.get("login") ?? "").trim() || undefined;
  const apiKey = String(formData.get("api_key") ?? "").trim();
  // Ticked checkboxes plus any extra model names typed under "More Odoo data".
  const picked = [...formData.getAll("models").map(String), String(formData.get("extra_models") ?? "")].join(",");
  const models = parseModels(formData.has("models") || formData.has("extra_models") ? picked : DEFAULT_ODOO_MODELS);
  let url: string;
  try {
    url = normaliseUrl(String(formData.get("url") ?? ""));
  } catch {
    return { error: "Enter the Odoo address, e.g. https://yourcompany.odoo.com" };
  }
  const db = String(formData.get("db") ?? "").trim() || guessOdooDb(url);
  if (!db) return { error: "Enter the database name — your Odoo administrator can find it under Settings → Database (or in the Odoo login page's database list)." };
  if (apiKey.length < 16) return { error: "Paste the Odoo API key." };
  if (models.length === 0) return { error: "Tick at least one kind of data to copy." };

  let mode: string;
  try {
    mode = (await OdooClient.connect({ url, db, login, apiKey })).mode;
  } catch (e) {
    return { error: e instanceof OdooError ? e.message : `Could not reach Odoo: ${e instanceof Error ? e.message : e}` };
  }

  const secretName = `odoo_${name.toLowerCase().replace(/[^a-z0-9]+/g, "_").slice(0, 40)}`;
  const { data: secretId, error: secretError } = await supabase.rpc("set_tenant_secret", {
    p_tenant_id: workspace.id,
    p_name: secretName,
    p_kind: "connector",
    p_provider: "odoo",
    p_secret: apiKey,
  });
  if (secretError) return { error: `Could not save the key: ${secretError.message}` };

  const { error } = await supabase.from("sources").upsert(
    {
      tenant_id: workspace.id,
      name,
      kind: mode === "json2" ? "odoo_json2" : "odoo_xmlrpc",
      config: { url, db, login: login ?? null, models, secret_name: secretName },
      secret_id: secretId,
      status: "pending",
      created_by: user.id,
    },
    { onConflict: "tenant_id,name" },
  );
  if (error) return { error: `Could not save the source: ${error.message}` };
  revalidatePath(`/app/${slug}`, "layout");
  return { ok: `Connected (${mode === "json2" ? "JSON-2 API" : "older JSON-RPC API"}). Click “Sync now” to copy the records.` };
}

type SourceRow = {
  id: string;
  tenant_id: string;
  kind: string;
  last_synced_at: string | null;
  config: { url: string; db: string; login: string | null; models: string[]; secret_name: string };
};

export async function syncSource(_prev: FormState, formData: FormData): Promise<FormState> {
  const slug = String(formData.get("slug"));
  const { supabase, user, workspace } = await context(slug);
  const { data: source } = await supabase
    .from("sources")
    .select("id, tenant_id, kind, last_synced_at, config")
    .eq("id", String(formData.get("source_id")))
    .eq("tenant_id", workspace.id)
    .maybeSingle<SourceRow>();
  if (!source || !source.kind.startsWith("odoo")) return { error: "Source not found." };

  const admin = createAdminClient();
  const { data: apiKey, error: keyError } = await admin.rpc("get_tenant_secret", {
    p_tenant_id: workspace.id,
    p_name: source.config.secret_name,
  });
  if (keyError || !apiKey) return { error: "The Odoo API key is missing. Connect the source again." };

  const startedAt = new Date().toISOString();
  try {
    const { results } = await syncOdoo(
      admin,
      source,
      { url: source.config.url, db: source.config.db, login: source.config.login ?? undefined, apiKey },
      source.config.models,
    );
    const total = results.reduce((n, r) => n + r.synced, 0);
    const failed = results.filter((r) => r.error);
    await admin
      .from("sources")
      .update({
        status: failed.length === results.length ? "error" : "active",
        last_synced_at: failed.length === results.length ? source.last_synced_at : startedAt,
        last_error: failed.length ? failed.map((r) => `${r.model}: ${r.error}`).join("; ").slice(0, 1000) : null,
      })
      .eq("id", source.id);
    if (total > 0) {
      await admin.from("usage_events").insert({
        tenant_id: workspace.id,
        metric: "synced_record",
        quantity: total,
        channel: "sync",
        user_id: user.id,
        metadata: { source_id: source.id, results },
      });
    }
    revalidatePath(`/app/${slug}`, "layout");
    const summary = results.map((r) => `${r.model}: ${r.error ? `failed (${r.error})` : r.synced}`).join(" · ");
    return failed.length ? { error: `Partly synced — ${summary}` } : { ok: `Synced ${total} records — ${summary}` };
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    await admin.from("sources").update({ status: "error", last_error: message.slice(0, 1000) }).eq("id", source.id);
    revalidatePath(`/app/${slug}`, "layout");
    return { error: message };
  }
}

export async function removeSource(formData: FormData) {
  const slug = String(formData.get("slug"));
  const { supabase, workspace } = await context(slug);
  const { data: source } = await supabase
    .from("sources")
    .select("id, config")
    .eq("id", String(formData.get("source_id")))
    .eq("tenant_id", workspace.id)
    .maybeSingle<{ id: string; config: { secret_name?: string } }>();
  if (!source) return;
  // Records go with the source (foreign key cascade); then drop the stored key.
  await supabase.from("sources").delete().eq("id", source.id);
  if (source.config.secret_name) {
    await supabase.rpc("delete_tenant_secret", { p_tenant_id: workspace.id, p_name: source.config.secret_name });
  }
  revalidatePath(`/app/${slug}`, "layout");
}
