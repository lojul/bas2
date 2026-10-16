"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import type { FormState } from "@/components/form-message";
import { getUser } from "@/lib/supabase/server";
import { OdooClient, OdooError, normaliseUrl } from "@/lib/odoo/client";
import { DEFAULT_ODOO_MODELS, guessOdooDb } from "@/lib/odoo/models";
import { normaliseSearchEndpoint, testSearch } from "@/lib/search/azure";
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
      status: "active",
      created_by: user.id,
    },
    { onConflict: "tenant_id,name" },
  );
  if (error) return { error: `Could not save the source: ${error.message}` };
  revalidatePath(`/app/${slug}`, "layout");
  return { ok: "Odoo is on. Ask and AI agents now read it live — nothing is copied into Genie." };
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
  // Turning Odoo off: forget the connection and its key. (Anything stored under the old copy design
  // goes with the source through the foreign key cascade.)
  await supabase.from("sources").delete().eq("id", source.id);
  if (source.config.secret_name) {
    await supabase.rpc("delete_tenant_secret", { p_tenant_id: workspace.id, p_name: source.config.secret_name });
  }
  revalidatePath(`/app/${slug}`, "layout");
}

// Turn on a customer's own Azure AI Search index (read live with a query key).
export async function connectSearch(_prev: FormState, formData: FormData): Promise<FormState> {
  const slug = String(formData.get("slug"));
  const { supabase, user, workspace } = await context(slug);
  const name = String(formData.get("name") ?? "").trim() || "Documents";
  const index = String(formData.get("index") ?? "").trim();
  const key = String(formData.get("query_key") ?? "").trim();
  const semantic = String(formData.get("semantic") ?? "").trim() || null;
  const vectorField = String(formData.get("vector_field") ?? "").trim() || null;
  let endpoint: string;
  try {
    endpoint = normaliseSearchEndpoint(String(formData.get("endpoint") ?? ""));
  } catch {
    return { error: "Enter the search service address, e.g. https://yourservice.search.windows.net" };
  }
  if (!index) return { error: "Enter the index name." };
  if (key.length < 20) return { error: "Paste the query key." };

  let count: number | null;
  try {
    ({ count } = await testSearch({ endpoint, index, key }));
  } catch (e) {
    return { error: e instanceof Error ? e.message : String(e) };
  }

  const secretName = `search_${name.toLowerCase().replace(/[^a-z0-9]+/g, "_").slice(0, 40)}`;
  const { data: secretId, error: secretError } = await supabase.rpc("set_tenant_secret", {
    p_tenant_id: workspace.id,
    p_name: secretName,
    p_kind: "connector",
    p_provider: "azure_search",
    p_secret: key,
  });
  if (secretError) return { error: `Could not save the key: ${secretError.message}` };

  const { error } = await supabase.from("sources").upsert(
    {
      tenant_id: workspace.id,
      name,
      kind: "azure_search",
      config: { endpoint, index, semantic, vector_field: vectorField, secret_name: secretName },
      secret_id: secretId,
      status: "active",
      created_by: user.id,
    },
    { onConflict: "tenant_id,name" },
  );
  if (error) return { error: `Could not save the source: ${error.message}` };
  revalidatePath(`/app/${slug}`, "layout");
  return { ok: `On — ${count ?? "the"} documents can now be searched live. Nothing is copied into Genie.` };
}
