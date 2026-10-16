"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import type { FormState } from "@/components/form-message";
import { createAdminClient } from "@/lib/supabase/admin";
import { getUser } from "@/lib/supabase/server";
import { OdooClient, OdooError, normaliseUrl } from "@/lib/odoo/client";
import { ODOO_MODEL_CHOICES, guessOdooDb } from "@/lib/odoo/models";
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

type ExistingSource = { id: string; name: string; config: { secret_name: string } };

// Edit mode: the form carries source_id. Returns the source being edited (in this workspace) and
// the key to use — the newly typed one, or else the saved one from Vault.
async function editTarget(
  supabase: Awaited<ReturnType<typeof context>>["supabase"],
  workspaceId: string,
  formData: FormData,
  typedKey: string,
): Promise<{ existing: ExistingSource | null; key: string; error?: string }> {
  const id = String(formData.get("source_id") ?? "");
  if (!id) return { existing: null, key: typedKey };
  const { data: existing } = await supabase
    .from("sources")
    .select("id, name, config")
    .eq("id", id)
    .eq("tenant_id", workspaceId)
    .maybeSingle<ExistingSource>();
  if (!existing) return { existing: null, key: typedKey, error: "Source not found." };
  if (typedKey) return { existing, key: typedKey };
  const { data: saved } = await createAdminClient().rpc("get_tenant_secret", { p_tenant_id: workspaceId, p_name: existing.config.secret_name });
  if (!saved) return { existing, key: "", error: "The saved key is missing — paste the key again." };
  return { existing, key: saved as string };
}

// Saves the source: updates the edited row in place, or inserts/replaces by name when new.
async function saveSource(
  supabase: Awaited<ReturnType<typeof context>>["supabase"],
  row: { tenant_id: string; name: string; kind: string; config: Record<string, unknown>; secret_id: string | null; created_by: string },
  existing: ExistingSource | null,
) {
  if (existing) {
    // Keep who created it and which workspace it belongs to; change the rest.
    const changes = { name: row.name, kind: row.kind, config: row.config, ...(row.secret_id ? { secret_id: row.secret_id } : {}) };
    return supabase.from("sources").update({ ...changes, status: "active", last_error: null }).eq("id", existing.id);
  }
  return supabase.from("sources").upsert({ ...row, status: "active" }, { onConflict: "tenant_id,name" });
}

const parseModels = (raw: string) =>
  [...new Set(raw.split(/[\s,]+/).map((m) => m.trim()).filter((m) => /^[a-z][a-z0-9_.]*$/.test(m)))].slice(0, 20);

export async function connectOdoo(_prev: FormState, formData: FormData): Promise<FormState> {
  const slug = String(formData.get("slug"));
  const { supabase, user, workspace } = await context(slug);
  const name = String(formData.get("name") ?? "").trim() || "Odoo";
  const login = String(formData.get("login") ?? "").trim() || undefined;
  const typedKey = String(formData.get("api_key") ?? "").trim();
  const extra = parseModels(String(formData.get("extra_models") ?? ""));
  let url: string;
  try {
    url = normaliseUrl(String(formData.get("url") ?? ""));
  } catch {
    return { error: "Enter the Odoo address, e.g. https://yourcompany.odoo.com" };
  }
  const db = String(formData.get("db") ?? "").trim() || guessOdooDb(url);
  if (!db) return { error: "Enter the database name — your Odoo administrator can find it under Settings → Database (or in the Odoo login page's database list)." };
  const target = await editTarget(supabase, workspace.id, formData, typedKey);
  if (target.error) return { error: target.error };
  const apiKey = target.key;
  if (apiKey.length < 16) return { error: "Paste the Odoo API key." };

  // No picking: Genie reads every known kind of data this Odoo user can read (contacts, leads,
  // C21 listings), plus any extra models typed under "Other Odoo data".
  let mode: string;
  let models: string[];
  try {
    const odoo = await OdooClient.connect({ url, db, login, apiKey });
    mode = odoo.mode;
    const candidates = [...new Set([...ODOO_MODEL_CHOICES.map((c) => c.model), ...extra])];
    const readable = await Promise.all(
      candidates.map((m) =>
        odoo
          .call(m, "search_count", { domain: [] })
          .then(() => m)
          .catch(() => null),
      ),
    );
    models = readable.filter((m): m is string => m !== null);
  } catch (e) {
    return { error: e instanceof OdooError ? e.message : `Could not reach Odoo: ${e instanceof Error ? e.message : e}` };
  }
  if (models.length === 0) {
    return { error: "Connected, but this Odoo user can't read contacts, CRM leads or listings. Give it read access in Odoo and try again." };
  }

  const secretName = target.existing?.config.secret_name ?? `odoo_${name.toLowerCase().replace(/[^a-z0-9]+/g, "_").slice(0, 40)}`;
  let secretId: string | null = null;
  if (typedKey) {
    const { data, error: secretError } = await supabase.rpc("set_tenant_secret", {
      p_tenant_id: workspace.id,
      p_name: secretName,
      p_kind: "connector",
      p_provider: "odoo",
      p_secret: apiKey,
    });
    if (secretError) return { error: `Could not save the key: ${secretError.message}` };
    secretId = data as string;
  }

  const { error } = await saveSource(
    supabase,
    {
      tenant_id: workspace.id,
      name,
      kind: mode === "json2" ? "odoo_json2" : "odoo_xmlrpc",
      config: { url, db, login: login ?? null, models, extra_models: extra, secret_name: secretName },
      secret_id: secretId,
      created_by: user.id,
    },
    target.existing,
  );
  if (error) return { error: `Could not save the source: ${error.message}` };
  revalidatePath(`/app/${slug}`, "layout");
  const labels = models.map((m) => ODOO_MODEL_CHOICES.find((c) => c.model === m)?.label ?? m).join(", ");
  return { ok: `${target.existing ? "Saved" : "Odoo is on"} — Genie can read ${labels}, live. Nothing is copied into Genie.` };
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
  const typedKey = String(formData.get("query_key") ?? "").trim();
  const semantic = String(formData.get("semantic") ?? "").trim() || null;
  const vectorField = String(formData.get("vector_field") ?? "").trim() || null;
  let endpoint: string;
  try {
    endpoint = normaliseSearchEndpoint(String(formData.get("endpoint") ?? ""));
  } catch {
    return { error: "Enter the search service address, e.g. https://yourservice.search.windows.net" };
  }
  if (!index) return { error: "Enter the index name." };
  const target = await editTarget(supabase, workspace.id, formData, typedKey);
  if (target.error) return { error: target.error };
  const key = target.key;
  if (key.length < 20) return { error: "Paste the query key." };

  let count: number | null;
  try {
    ({ count } = await testSearch({ endpoint, index, key }));
  } catch (e) {
    return { error: e instanceof Error ? e.message : String(e) };
  }

  const secretName = target.existing?.config.secret_name ?? `search_${name.toLowerCase().replace(/[^a-z0-9]+/g, "_").slice(0, 40)}`;
  let secretId: string | null = null;
  if (typedKey) {
    const { data, error: secretError } = await supabase.rpc("set_tenant_secret", {
      p_tenant_id: workspace.id,
      p_name: secretName,
      p_kind: "connector",
      p_provider: "azure_search",
      p_secret: key,
    });
    if (secretError) return { error: `Could not save the key: ${secretError.message}` };
    secretId = data as string;
  }

  const { error } = await saveSource(
    supabase,
    {
      tenant_id: workspace.id,
      name,
      kind: "azure_search",
      config: { endpoint, index, semantic, vector_field: vectorField, secret_name: secretName },
      secret_id: secretId,
      created_by: user.id,
    },
    target.existing,
  );
  if (error) return { error: `Could not save the source: ${error.message}` };
  revalidatePath(`/app/${slug}`, "layout");
  return { ok: `${target.existing ? "Saved" : "On"} — ${count ?? "the"} documents can now be searched live. Nothing is copied into Genie.` };
}

// "Test connection" on a switched-on source: reads it live with the saved key and reports what it
// found. Records the outcome on the source (status, last_error) so the sidebar dot matches.
export async function testSource(_prev: FormState, formData: FormData): Promise<FormState> {
  const slug = String(formData.get("slug"));
  const { supabase, workspace } = await context(slug);
  const { data: source } = await supabase
    .from("sources")
    .select("id, name, kind, config")
    .eq("id", String(formData.get("source_id")))
    .eq("tenant_id", workspace.id)
    .maybeSingle<{
      id: string;
      name: string;
      kind: string;
      config: { secret_name: string; url?: string; db?: string; login?: string | null; models?: string[]; endpoint?: string; index?: string };
    }>();
  if (!source) return { error: "Source not found." };

  const admin = createAdminClient();
  const started = Date.now();
  const record = (error: string | null) =>
    admin.from("sources").update({ status: error ? "error" : "active", last_error: error }).eq("id", source.id);
  try {
    const { data: key, error: keyError } = await admin.rpc("get_tenant_secret", { p_tenant_id: workspace.id, p_name: source.config.secret_name });
    if (keyError || !key) throw new Error("The saved key is missing. Click Edit and paste the key again.");
    let found: string;
    if (source.kind.startsWith("odoo")) {
      const odoo = await OdooClient.open(
        { url: source.config.url ?? "", db: source.config.db ?? "", login: source.config.login ?? undefined, apiKey: key as string },
        source.kind === "odoo_json2" ? "json2" : "jsonrpc",
      );
      const counts = await Promise.all(
        (source.config.models ?? []).map(async (m) => {
          const n = await odoo.call<number>(m, "search_count", { domain: [] });
          return `${ODOO_MODEL_CHOICES.find((c) => c.model === m)?.label ?? m} ${n.toLocaleString()}`;
        }),
      );
      found = counts.join(" · ");
    } else if (source.kind === "azure_search") {
      const { count } = await testSearch({ endpoint: source.config.endpoint ?? "", index: source.config.index ?? "", key: key as string });
      found = `${(count ?? 0).toLocaleString()} documents`;
    } else {
      return { error: "This kind of source can't be tested yet." };
    }
    await record(null);
    revalidatePath(`/app/${slug}`, "layout");
    return { ok: `✓ Connected in ${((Date.now() - started) / 1000).toFixed(1)} s — ${found}.` };
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e);
    await record(message.slice(0, 1000));
    revalidatePath(`/app/${slug}`, "layout");
    return { error: `✗ Failed — ${message}` };
  }
}
