import "server-only";
import { OdooClient, type OdooConfig, type OdooMode } from "./client";
import { ODOO_MODEL_CHOICES } from "./models";

// Genie's tools over a live Odoo (decided 2026-10-16: Genie stores no copy of customer data).
// Every call reads Odoo at question time with the workspace's own API key; nothing is saved.
// Record ids are "<odoo model>:<odoo id>", e.g. "res.partner:42".

type FieldMeta = { type: string; string: string; store?: boolean; selection?: [string, string][] };
type Row = Record<string, unknown> & { id: number; display_name?: string };

export type LiveOdoo = { name: string; url: string; models: string[]; odoo: OdooClient };

const OBJECT_TYPE: Record<string, string> = {
  "res.partner": "contact",
  "crm.lead": "lead",
  x_c21_listing: "listing",
  "product.template": "product",
  "sale.order": "sales_order",
};
const READABLE = new Set(["char", "text", "html", "selection", "integer", "float", "monetary", "date", "datetime", "boolean", "many2one"]);
const SKIP = /^(message_|activity_|website_message|__|create_uid$|write_uid$|access_|image_|avatar_|password|signup_|totp)/;
const SEARCHABLE = new Set(["char", "text"]);
const MAX_SEARCH_FIELDS = 8;
const SNIPPET_FIELDS = 6;

export async function openLiveOdoo(
  source: { name: string; kind: string; config: { url: string; db: string; login?: string | null; models: string[] } },
  apiKey: string,
): Promise<LiveOdoo> {
  const cfg: OdooConfig = { url: source.config.url, db: source.config.db, login: source.config.login ?? undefined, apiKey };
  const mode: OdooMode = source.kind === "odoo_json2" ? "json2" : "jsonrpc";
  return { name: source.name, url: source.config.url, models: source.config.models, odoo: await OdooClient.open(cfg, mode) };
}

// Field descriptions change rarely; keep them for 10 minutes per Odoo address and model.
const fieldCache = new Map<string, { at: number; fields: Record<string, FieldMeta> }>();
async function fieldsOf(live: LiveOdoo, model: string) {
  const key = `${live.url}|${model}`;
  const hit = fieldCache.get(key);
  if (hit && Date.now() - hit.at < 10 * 60_000) return hit.fields;
  const fields = await live.odoo.call<Record<string, FieldMeta>>(model, "fields_get", {
    attributes: ["type", "string", "store", "selection"],
  });
  fieldCache.set(key, { at: Date.now(), fields });
  return fields;
}

const typeOf = (model: string) => OBJECT_TYPE[model] ?? model;
const labelOf = (model: string) => ODOO_MODEL_CHOICES.find((c) => c.model === model)?.label ?? model;

function readable(v: unknown, f: FieldMeta): string | number | boolean | null {
  if (v === false && f.type !== "boolean") return null;
  if (v === null || v === undefined) return null;
  if (f.type === "many2one") return Array.isArray(v) ? String(v[1] ?? v[0]) : String(v);
  if (f.type === "selection") return f.selection?.find(([k]) => k === v)?.[1] ?? String(v);
  if (f.type === "html") return String(v).replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  if (typeof v === "number" || typeof v === "boolean") return v;
  return String(v);
}

function readableFields(fields: Record<string, FieldMeta>) {
  return Object.entries(fields).filter(([name, f]) => f.store !== false && READABLE.has(f.type) && !SKIP.test(name));
}

// Odoo domain: every word must match at least one of the fields (AND of ORs).
function wordsDomain(query: string, fields: string[]): unknown[] {
  const words = query.split(/\s+/).map((w) => w.trim()).filter(Boolean).slice(0, 6);
  const domain: unknown[] = [];
  for (const word of words) {
    const ors = fields.map((f) => [f, "ilike", word]);
    for (let i = 1; i < ors.length; i++) domain.push("|");
    domain.push(...ors);
  }
  return domain;
}

function pickModels(live: LiveOdoo, objectType?: string | null) {
  if (!objectType) return live.models;
  return live.models.filter((m) => m === objectType || typeOf(m) === objectType);
}

export async function liveWorkspaceInfo(live: LiveOdoo, workspaceName: string) {
  const types = await Promise.all(
    live.models.map(async (model) => {
      let count: number | null = null;
      try {
        count = await live.odoo.call<number>(model, "search_count", { domain: [] });
      } catch {
        count = null;
      }
      return { object_type: typeOf(model), label: labelOf(model), odoo_model: model, count };
    }),
  );
  return {
    workspace: workspaceName,
    sources: [{ name: live.name, kind: "Odoo (read live, nothing stored in Genie)", url: live.url }],
    record_types: types,
  };
}

export async function liveSearchRecords(live: LiveOdoo, query: string | null | undefined, objectType: string | null | undefined, limit: number) {
  const models = pickModels(live, objectType);
  if (models.length === 0) return { results: [], note: `No record type "${objectType}". Call workspace_info for the list.` };
  const per = Math.max(3, Math.ceil(limit / models.length));
  const results: unknown[] = [];
  const errors: string[] = [];
  await Promise.all(
    models.map(async (model) => {
      try {
        const fields = await fieldsOf(live, model);
        const readableList = readableFields(fields);
        const searchFields = readableList.filter(([, f]) => SEARCHABLE.has(f.type)).map(([n]) => n).slice(0, MAX_SEARCH_FIELDS);
        if (searchFields.length === 0) return;
        const snippetFields = readableList
          .filter(([n]) => n !== "display_name")
          .slice(0, SNIPPET_FIELDS)
          .map(([n]) => n);
        const q = query?.trim();
        const rows = await live.odoo.call<Row[]>(model, "search_read", {
          domain: q ? wordsDomain(q, searchFields) : [],
          fields: ["display_name", ...snippetFields],
          limit: per,
          order: "write_date desc",
        });
        for (const row of rows) {
          const snippet = snippetFields
            .map((n) => {
              const v = readable(row[n], fields[n]);
              return v === null || v === "" ? null : `${fields[n].string}: ${v}`;
            })
            .filter(Boolean)
            .join(" · ")
            .slice(0, 300);
          results.push({ id: `${model}:${row.id}`, type: typeOf(model), title: row.display_name ?? `${model} ${row.id}`, snippet });
        }
      } catch (e) {
        errors.push(`${labelOf(model)}: ${e instanceof Error ? e.message : e}`);
      }
    }),
  );
  return { results: results.slice(0, limit), ...(errors.length ? { errors } : {}) };
}

export async function liveGetRecord(live: LiveOdoo, id: string) {
  const m = /^([a-z][a-z0-9_.]*):(\d+)$/.exec(id.trim());
  if (!m) throw new Error('Record ids look like "res.partner:42" (from search_records or find_contact).');
  const [, model, odooId] = m;
  if (!live.models.includes(model)) throw new Error(`${model} is not one of the data types this workspace reads.`);
  const fields = await fieldsOf(live, model);
  const names = readableFields(fields).map(([n]) => n).slice(0, 150);
  // search_read (not read) so the same call works on JSON-2 and the older JSON-RPC API.
  const rows = await live.odoo.call<Row[]>(model, "search_read", {
    domain: [["id", "=", Number(odooId)]],
    fields: ["display_name", ...names],
    limit: 1,
  });
  const row = rows[0];
  if (!row) return { found: false, id };
  const out: Record<string, unknown> = {};
  for (const n of names) {
    const v = readable(row[n], fields[n]);
    if (v !== null && v !== "") out[fields[n].string || n] = v;
  }
  return { id, type: typeOf(model), title: row.display_name ?? id, fields: out, odoo_link: `${live.url}/odoo/${model}/${odooId}` };
}

export async function liveFindContact(live: LiveOdoo, query: string, limit: number) {
  if (!live.models.includes("res.partner")) return { results: [], note: "This workspace does not read Odoo contacts." };
  const q = query.trim();
  const digits = q.replace(/\D/g, "");
  const conds: unknown[] = [
    ["name", "ilike", q],
    ["email", "ilike", q],
    ["phone", "ilike", q],
    ["mobile", "ilike", q],
  ];
  // Phone numbers are stored in many formats; also match on the last 8 digits.
  if (digits.length >= 6) conds.push(["phone", "ilike", digits.slice(-8)], ["mobile", "ilike", digits.slice(-8)]);
  const fields = await fieldsOf(live, "res.partner");
  const usable = conds.filter((c) => (c as [string])[0] in fields);
  const domain: unknown[] = [];
  for (let i = 1; i < usable.length; i++) domain.push("|");
  domain.push(...usable);
  const want = ["display_name", "email", "phone", "mobile", "parent_id", "function", "city"].filter((f) => f === "display_name" || f in fields);
  const rows = await live.odoo.call<Row[]>("res.partner", "search_read", { domain, fields: want, limit });
  return {
    results: rows.map((r) => ({
      id: `res.partner:${r.id}`,
      name: r.display_name,
      company: Array.isArray(r.parent_id) ? r.parent_id[1] : null,
      email: r.email || null,
      phone: r.phone || null,
      mobile: r.mobile || null,
      job: r.function || null,
      city: r.city || null,
    })),
  };
}
