import "server-only";
import type { SupabaseClient } from "@supabase/supabase-js";
import { OdooClient, type OdooConfig } from "./odoo";

// Copies Odoo records into public.records (service role). Incremental by write_date after the
// first run. Field values are kept as readable text: many2one -> name, selection -> label.

type FieldMeta = { type: string; string: string; store?: boolean; selection?: [string, string][] };
type OdooRow = Record<string, unknown> & { id: number };

const OBJECT_TYPE: Record<string, string> = {
  "res.partner": "contact",
  "crm.lead": "lead",
  x_c21_listing: "listing",
  "product.template": "product",
  "sale.order": "sales_order",
};
const SYNC_TYPES = new Set(["char", "text", "html", "selection", "integer", "float", "monetary", "date", "datetime", "boolean", "many2one"]);
const SKIP = /^(message_|activity_|website_message|__|create_uid$|write_uid$|access_|image_|avatar_)/;
const PAGE = 500;
const MAX_PER_MODEL = 5000;
const MAX_FIELDS = 120;

export type ModelResult = { model: string; synced: number; error?: string };

export async function syncOdoo(
  admin: SupabaseClient,
  source: { id: string; tenant_id: string; last_synced_at: string | null },
  cfg: OdooConfig,
  models: string[],
): Promise<{ mode: string; results: ModelResult[] }> {
  const odoo = await OdooClient.connect(cfg);
  const since = source.last_synced_at ? toOdooDate(new Date(new Date(source.last_synced_at).getTime() - 10 * 60_000)) : null;
  const results: ModelResult[] = [];
  for (const model of models) {
    try {
      results.push({ model, synced: await syncModel(admin, odoo, source, model, since) });
    } catch (e) {
      results.push({ model, synced: 0, error: e instanceof Error ? e.message : String(e) });
    }
  }
  return { mode: odoo.mode, results };
}

async function syncModel(admin: SupabaseClient, odoo: OdooClient, source: { id: string; tenant_id: string }, model: string, since: string | null) {
  const meta = await odoo.call<Record<string, FieldMeta>>(model, "fields_get", { attributes: ["type", "string", "store", "selection"] });
  const fields = Object.entries(meta)
    .filter(([name, f]) => f.store !== false && SYNC_TYPES.has(f.type) && !SKIP.test(name))
    .slice(0, MAX_FIELDS);
  const names = [...new Set(["display_name", "write_date", ...fields.map(([n]) => n)])].filter((n) => n in meta);
  const domain = since ? [["write_date", ">", since]] : [];
  const objectType = OBJECT_TYPE[model] ?? model;

  let synced = 0;
  for (let offset = 0; offset < MAX_PER_MODEL; offset += PAGE) {
    const rows = await odoo.call<OdooRow[]>(model, "search_read", { domain, fields: names, limit: PAGE, offset, order: "id" });
    if (rows.length === 0) break;
    const records = rows.map((row) => toRecord(row, model, objectType, fields, source));
    const { error } = await admin.from("records").upsert(records, { onConflict: "source_id,object_type,external_id" });
    if (error) throw new Error(`saving ${model}: ${error.message}`);
    synced += rows.length;
    if (rows.length < PAGE) break;
  }
  return synced;
}

function toRecord(
  row: OdooRow,
  model: string,
  objectType: string,
  fields: [string, FieldMeta][],
  source: { id: string; tenant_id: string },
) {
  const data: Record<string, unknown> = { odoo_model: model, odoo_id: row.id };
  const lines: string[] = [];
  for (const [name, f] of fields) {
    const v = readable(row[name], f);
    if (v === null || v === "") continue;
    data[name] = v;
    if (["char", "text", "html", "selection", "many2one", "monetary", "float", "integer", "date"].includes(f.type)) {
      lines.push(`${f.string}: ${v}`);
    }
  }
  if (model === "res.partner") data.company = data.parent_id ?? data.company_name ?? null;
  const title = String(row.display_name || row.name || row.x_name || `${model} ${row.id}`);
  return {
    tenant_id: source.tenant_id,
    source_id: source.id,
    object_type: objectType,
    external_id: `${model}:${row.id}`,
    title,
    body: lines.join("\n").slice(0, 8000),
    data,
    source_updated_at: typeof row.write_date === "string" ? new Date(`${row.write_date.replace(" ", "T")}Z`).toISOString() : null,
    synced_at: new Date().toISOString(),
    deleted_at: null,
  };
}

function readable(v: unknown, f: FieldMeta): string | number | boolean | null {
  if (v === false && f.type !== "boolean") return null;
  if (v === null || v === undefined) return null;
  if (f.type === "many2one") return Array.isArray(v) ? String(v[1] ?? v[0]) : String(v);
  if (f.type === "selection") return f.selection?.find(([k]) => k === v)?.[1] ?? String(v);
  if (f.type === "html") return String(v).replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  if (typeof v === "number" || typeof v === "boolean") return v;
  return String(v);
}

const toOdooDate = (d: Date) => d.toISOString().slice(0, 19).replace("T", " ");
