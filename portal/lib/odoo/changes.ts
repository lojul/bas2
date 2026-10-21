import "server-only";
import { createAdminClient } from "@/lib/supabase/admin";
import type { Role } from "@/lib/roles";
import { OdooClient } from "./client";
import { ODOO_KINDS, ODOO_MODEL_CHOICES } from "./models";

// Changes in Odoo from Ask (user decision 2026-10-17). Genie never writes on its own: a tool call
// only creates a *draft* (odoo_actions row); a person presses Confirm, and only then the server writes
// to Odoo with the workspace's dedicated "Genie" Odoo user key (Vault secret ODOO_WRITE_SECRET).
// Controls, all in Settings → Data sources → "Changes in Odoo": master switch (off by default), a tick
// and "who may ask" per action, the fields that may be updated, and a daily limit. Web (Ask) only —
// on Slack and WhatsApp Genie can't yet tell which member is asking.

export const ODOO_WRITE_SECRET = "odoo_write_key";

export type ChangeAction = "create_lead" | "create_contact" | "add_note" | "schedule_follow_up" | "update_record";
export type Who = "member" | "admin";
export type ChangeSettings = {
  enabled?: boolean;
  actions?: Partial<Record<ChangeAction, { on?: boolean; who?: Who }>>;
  daily_limit?: number;
  update_fields?: string[]; // "<model>:<field>"
};

export const CHANGE_ACTIONS: { id: ChangeAction; label: string; hint: string; defaultOn: boolean; defaultWho: Who }[] = [
  { id: "create_lead", label: "Create a CRM lead", hint: "Contact name, phone, email, company, notes", defaultOn: true, defaultWho: "member" },
  { id: "create_contact", label: "Create a contact", hint: "Name, phone, email, company, notes", defaultOn: true, defaultWho: "member" },
  { id: "add_note", label: "Add a note to a record", hint: "Shown in the record's history in Odoo", defaultOn: true, defaultWho: "member" },
  { id: "schedule_follow_up", label: "Schedule a follow-up", hint: "A to-do with a due date on a record", defaultOn: true, defaultWho: "member" },
  { id: "update_record", label: "Update fields on a record", hint: "Only the fields ticked below", defaultOn: false, defaultWho: "admin" },
];
export const DEFAULT_DAILY_LIMIT = 50;

export function actionOn(s: ChangeSettings, a: ChangeAction) {
  const meta = CHANGE_ACTIONS.find((x) => x.id === a)!;
  return { on: s.actions?.[a]?.on ?? meta.defaultOn, who: s.actions?.[a]?.who ?? meta.defaultWho };
}
const roleAllowed = (role: Role, who: Who) => (who === "member" ? role !== "viewer" : role === "owner" || role === "admin");

// Field types Genie may write when "update fields" is allowed.
const WRITABLE = new Set(["char", "text", "selection", "integer", "float", "monetary", "date", "boolean"]);
const SKIP = /^(message_|activity_|website_|__|create_|write_|access_|image_|avatar_|password|signup_|totp|id$|display_name$)/;
type FieldMeta = { type: string; string: string; store?: boolean; readonly?: boolean; selection?: [string, string][] };

type SourceRow = { kind: string; config: { url?: string; db?: string; models?: string[] } };

async function loadContext(tenantId: string) {
  const admin = createAdminClient();
  const [{ data: tenant }, { data: source }] = await Promise.all([
    admin.from("tenants").select("settings").eq("id", tenantId).single<{ settings: { odoo_changes?: ChangeSettings } | null }>(),
    admin.from("sources").select("kind, config").eq("tenant_id", tenantId).in("kind", ODOO_KINDS).neq("status", "paused").limit(1).maybeSingle<SourceRow>(),
  ]);
  return { admin, settings: tenant?.settings?.odoo_changes ?? {}, source };
}

export async function changeSettingsFor(tenantId: string) {
  const { settings, source } = await loadContext(tenantId);
  return { settings, odoo: source };
}

// The Odoo connection used for changes: same Odoo address, the Genie user's own key, JSON-2 only.
export async function writeClient(tenantId: string, keyOverride?: string) {
  const { admin, source } = await loadContext(tenantId);
  if (!source?.config.url) throw new Error("Odoo is not switched on for this workspace.");
  if (source.kind === "odoo_mcp") throw new Error("Odoo is connected with an MCP key, which can only read. Changes need a key with Scope \"RPC\".");
  if (source.kind !== "odoo_json2") throw new Error("Changes need Odoo 19 or later (the JSON-2 API).");
  let key = keyOverride;
  if (!key) {
    const { data } = await admin.rpc("get_tenant_secret", { p_tenant_id: tenantId, p_name: ODOO_WRITE_SECRET });
    key = (data as string | null) ?? undefined;
  }
  if (!key) throw new Error("No key for the Genie Odoo user yet (Settings → Data sources → Changes in Odoo).");
  return { odoo: await OdooClient.open({ url: source.config.url, db: source.config.db ?? "", apiKey: key }, "json2"), url: source.config.url, models: source.config.models ?? [] };
}

// Who the key belongs to, and whether it may create leads — for Test connection.
export async function describeWriteUser(tenantId: string, key?: string) {
  const { odoo } = await writeClient(tenantId, key);
  const ctx = await odoo.call<{ uid?: number }>("res.users", "context_get", {});
  const [user] = await odoo.call<{ name: string; login: string }[]>("res.users", "search_read", {
    domain: [["id", "=", ctx.uid ?? 0]],
    fields: ["name", "login"],
    limit: 1,
  });
  let canCreateLeads: boolean | null = null;
  try {
    canCreateLeads = await odoo.call<boolean>("crm.lead", "has_access", { operation: "create" });
  } catch {
    try {
      canCreateLeads = await odoo.call<boolean>("crm.lead", "check_access_rights", { operation: "create", raise_exception: false });
    } catch {
      canCreateLeads = null;
    }
  }
  return { name: user?.name ?? "?", login: user?.login ?? "?", canCreateLeads };
}

// Fields an admin may allow Genie to update, per readable model (for the settings card).
export async function updatableFields(tenantId: string) {
  const { odoo, models } = await writeClient(tenantId).catch(() => ({ odoo: null, models: [] as string[] }));
  if (!odoo) return [];
  const out: { model: string; label: string; fields: { name: string; label: string }[] }[] = [];
  for (const model of models) {
    try {
      const fields = await odoo.call<Record<string, FieldMeta>>(model, "fields_get", { attributes: ["type", "string", "store", "readonly"] });
      out.push({
        model,
        label: ODOO_MODEL_CHOICES.find((c) => c.model === model)?.label ?? model,
        fields: Object.entries(fields)
          .filter(([n, f]) => WRITABLE.has(f.type) && f.store !== false && !f.readonly && !SKIP.test(n))
          .map(([name, f]) => ({ name, label: f.string || name }))
          .sort((a, b) => a.label.localeCompare(b.label)),
      });
    } catch {
      // The Genie user can't read this model; nothing to offer.
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Tools offered to the AI (only the actions switched on and allowed for this member)
// ---------------------------------------------------------------------------

export type Actor = { userId: string; email: string; role: Role; chatId: string | null };

export async function changeToolsFor(tenantId: string, actor: Actor | null) {
  if (!actor) return { tools: [], allowedFields: [] as string[] };
  const { settings, source } = await loadContext(tenantId);
  if (!settings.enabled || source?.kind !== "odoo_json2") return { tools: [], allowedFields: [] as string[] };
  const allowed = CHANGE_ACTIONS.filter((a) => {
    const s = actionOn(settings, a.id);
    return s.on && roleAllowed(actor.role, s.who);
  }).map((a) => a.id);
  const fields = settings.update_fields ?? [];
  const tools = TOOL_SPECS.filter((t) => allowed.includes(t.name as ChangeAction) && (t.name !== "update_record" || fields.length > 0)).map((t) =>
    t.name === "update_record"
      ? { ...t, description: `${t.description} Fields that may be changed (record type: field): ${fields.join(", ")}.` }
      : t,
  );
  return { tools, allowedFields: fields };
}

const RECORD_ARG = { type: "string", description: 'Record id exactly as returned by search_records / find_contact / get_record, e.g. "crm.lead:42".' };
const TOOL_SPECS = [
  {
    name: "create_lead",
    description:
      "Prepare a new CRM lead in Odoo. This only makes a draft: the user must press Confirm under your answer before anything is saved. Use when someone asks to create/log a lead or enquiry.",
    input_schema: {
      type: "object" as const,
      properties: {
        contact_name: { type: "string", description: "The client's name." },
        phone: { type: "string" },
        email: { type: "string" },
        company: { type: "string" },
        title: { type: "string", description: "Short lead title, e.g. '3-bed rental Taikoo Shing'." },
        notes: { type: "string", description: "What the client wants (property, budget, timing)." },
      },
      required: ["contact_name"],
      additionalProperties: false as const,
    },
  },
  {
    name: "create_contact",
    description: "Prepare a new contact (person or company) in Odoo. Only a draft until the user presses Confirm. Check with find_contact first that it doesn't exist.",
    input_schema: {
      type: "object" as const,
      properties: {
        name: { type: "string" },
        phone: { type: "string" },
        email: { type: "string" },
        company: { type: "string" },
        notes: { type: "string" },
      },
      required: ["name"],
      additionalProperties: false as const,
    },
  },
  {
    name: "add_note",
    description: "Prepare a note on an existing Odoo record (shown in its history). Only a draft until the user presses Confirm. Find the record first.",
    input_schema: {
      type: "object" as const,
      properties: { record: RECORD_ARG, note: { type: "string" } },
      required: ["record", "note"],
      additionalProperties: false as const,
    },
  },
  {
    name: "schedule_follow_up",
    description: "Prepare a follow-up to-do on an existing Odoo record, assigned to the person asking. Only a draft until the user presses Confirm.",
    input_schema: {
      type: "object" as const,
      properties: {
        record: RECORD_ARG,
        summary: { type: "string", description: "What to do, e.g. 'Call back about viewing'." },
        due_date: { type: "string", description: "YYYY-MM-DD. Work out dates like 'next Monday' from today's date." },
        note: { type: "string" },
      },
      required: ["record", "summary", "due_date"],
      additionalProperties: false as const,
    },
  },
  {
    name: "update_record",
    description: "Prepare changes to fields of an existing Odoo record. Only a draft until the user presses Confirm. Only the allowed fields can be changed.",
    input_schema: {
      type: "object" as const,
      properties: {
        record: RECORD_ARG,
        changes: { type: "object", description: "Field technical name → new value, e.g. {\"x_price\": 32000}.", additionalProperties: true },
      },
      required: ["record", "changes"],
      additionalProperties: false as const,
    },
  },
];
export const CHANGE_TOOL_NAMES = new Set(TOOL_SPECS.map((t) => t.name));

// ---------------------------------------------------------------------------
// Drafts
// ---------------------------------------------------------------------------

type Draft = { title: string; lines: [string, string][]; vals?: Record<string, unknown>; note?: string; summary?: string; due_date?: string };
export type ProposalView = {
  id: string;
  action: ChangeAction;
  label: string;
  title: string | null;
  lines: [string, string][];
  status: "proposed" | "done" | "cancelled" | "failed" | "expired";
  requested_email: string | null;
  decided_email: string | null;
  error: string | null;
  link: string | null;
  canDecide: boolean;
};

const str = (v: unknown, max = 500) => (typeof v === "string" ? v.trim().slice(0, max) : v == null ? "" : String(v).trim().slice(0, max));
const labelOf = (a: ChangeAction) => CHANGE_ACTIONS.find((x) => x.id === a)!.label;

function parseRecord(id: unknown, models: string[]) {
  const [model, raw] = str(id, 100).split(":");
  const n = Number(raw);
  if (!model || !Number.isInteger(n) || n <= 0) throw new Error('Give the record id as returned by search, e.g. "crm.lead:42".');
  if (!models.includes(model)) throw new Error(`Genie can't change ${model} records.`);
  return { model, id: n };
}

// Checks the switches and the daily limit; with a role, also who may ask (checked when the draft is
// made — at Confirm the requester's draft is re-checked without it).
async function guard(tenantId: string, action: ChangeAction, role: Role | null) {
  const { admin, settings } = await loadContext(tenantId);
  if (!settings.enabled) throw new Error("Changes in Odoo are switched off for this workspace.");
  const s = actionOn(settings, action);
  if (!s.on) throw new Error(`"${labelOf(action)}" is switched off for this workspace.`);
  if (role && !roleAllowed(role, s.who)) throw new Error(`Only owners and admins may ask for "${labelOf(action)}".`);
  const since = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
  const { count } = await admin.from("odoo_actions").select("id", { count: "exact", head: true }).eq("tenant_id", tenantId).eq("status", "done").gte("decided_at", since);
  const limit = settings.daily_limit ?? DEFAULT_DAILY_LIMIT;
  if ((count ?? 0) >= limit) throw new Error(`The daily limit of ${limit} changes in Odoo has been reached. Try again tomorrow or ask an admin to raise it.`);
  return { admin, settings };
}

// A tool call from the AI → a draft the person must confirm. Returns what the AI should tell them.
export async function proposeChange(tenantId: string, actor: Actor, action: ChangeAction, args: Record<string, unknown>) {
  const { admin, settings } = await guard(tenantId, action, actor.role);
  const { odoo, models } = await writeClient(tenantId);
  let model = "";
  let recordId: number | null = null;
  let draft: Draft;

  if (action === "create_lead") {
    const name = str(args.contact_name, 120);
    if (!name) throw new Error("A lead needs the client's name.");
    const notes = str(args.notes, 2000);
    model = "crm.lead";
    draft = {
      title: str(args.title, 120) || `${name} — enquiry`,
      vals: { contact_name: name, partner_name: str(args.company, 120) || false, phone: str(args.phone, 40) || false, email_from: str(args.email, 120) || false, description: notes || false },
      lines: [],
    };
    draft.vals!.name = draft.title;
    draft.lines = [["Title", draft.title], ["Client", name], ["Phone", str(args.phone, 40)], ["Email", str(args.email, 120)], ["Company", str(args.company, 120)], ["Notes", notes]];
  } else if (action === "create_contact") {
    const name = str(args.name, 120);
    if (!name) throw new Error("A contact needs a name.");
    model = "res.partner";
    draft = {
      title: name,
      vals: { name, phone: str(args.phone, 40) || false, email: str(args.email, 120) || false, company_name: str(args.company, 120) || false, comment: str(args.notes, 2000) || false },
      lines: [["Name", name], ["Phone", str(args.phone, 40)], ["Email", str(args.email, 120)], ["Company", str(args.company, 120)], ["Notes", str(args.notes, 2000)]],
    };
  } else {
    const rec = parseRecord(args.record, models);
    model = rec.model;
    recordId = rec.id;
    const [row] = await odoo.call<{ display_name: string }[]>(model, "search_read", { domain: [["id", "=", rec.id]], fields: ["display_name"], limit: 1 });
    if (!row) throw new Error("That record wasn't found in Odoo (or the Genie Odoo user can't see it).");
    const title = row.display_name;
    if (action === "add_note") {
      const note = str(args.note, 4000);
      if (!note) throw new Error("The note is empty.");
      draft = { title, note, lines: [["Record", title], ["Note", note]] };
    } else if (action === "schedule_follow_up") {
      const due = str(args.due_date, 10);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(due)) throw new Error("Give the due date as YYYY-MM-DD.");
      draft = { title, summary: str(args.summary, 200), due_date: due, note: str(args.note, 2000), lines: [["Record", title], ["To do", str(args.summary, 200)], ["Due", due], ["For", actor.email], ["Note", str(args.note, 2000)]] };
    } else {
      const changes = (args.changes ?? {}) as Record<string, unknown>;
      const allowed = new Set((settings.update_fields ?? []).filter((f) => f.startsWith(`${model}:`)).map((f) => f.slice(model.length + 1)));
      const fields = await odoo.call<Record<string, FieldMeta>>(model, "fields_get", { attributes: ["type", "string", "selection"] });
      const vals: Record<string, unknown> = {};
      const lines: [string, string][] = [["Record", title]];
      for (const [name, raw] of Object.entries(changes)) {
        const f = fields[name];
        if (!f || !allowed.has(name)) throw new Error(`Genie may not change the field "${name}" on ${model}. Allowed: ${[...allowed].join(", ") || "none"}.`);
        vals[name] = coerce(raw, f, name);
        const shown = f.type === "selection" ? (f.selection?.find(([k]) => k === vals[name])?.[1] ?? String(vals[name])) : String(vals[name]);
        lines.push([f.string || name, shown]);
      }
      if (!Object.keys(vals).length) throw new Error("No changes given.");
      draft = { title, vals, lines };
    }
  }

  draft.lines = draft.lines.filter(([, v]) => v);
  const { data, error } = await admin
    .from("odoo_actions")
    .insert({ tenant_id: tenantId, chat_id: actor.chatId, requested_by: actor.userId, requested_email: actor.email, action, model, record_id: recordId, draft })
    .select("id")
    .single();
  if (error || !data) throw new Error(`Could not prepare the change: ${error?.message}`);
  return {
    draft_id: data.id,
    status: "waiting for confirmation",
    preview: Object.fromEntries(draft.lines),
    instruction: "Nothing is saved yet. Tell the user to check the draft card below your answer and press Confirm (or Cancel). Do not say it has been created.",
  };
}

function coerce(v: unknown, f: FieldMeta, name: string): unknown {
  switch (f.type) {
    case "integer": {
      const n = Number(v);
      if (!Number.isInteger(n)) throw new Error(`${name} needs a whole number.`);
      return n;
    }
    case "float":
    case "monetary": {
      const n = Number(String(v).replace(/[, $]/g, ""));
      if (!Number.isFinite(n)) throw new Error(`${name} needs a number.`);
      return n;
    }
    case "boolean":
      return v === true || v === "true" || v === "yes" || v === 1;
    case "date": {
      const s = String(v);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) throw new Error(`${name} needs a date as YYYY-MM-DD.`);
      return s;
    }
    case "selection": {
      const s = String(v);
      const hit = f.selection?.find(([k, l]) => k === s || l.toLowerCase() === s.toLowerCase());
      if (!hit) throw new Error(`${name} must be one of: ${(f.selection ?? []).map(([, l]) => l).join(", ")}.`);
      return hit[0];
    }
    default:
      return String(v ?? "").slice(0, 4000);
  }
}

type Row = {
  id: string;
  tenant_id: string;
  action: ChangeAction;
  model: string;
  record_id: number | null;
  draft: Draft | null;
  status: ProposalView["status"];
  requested_by: string | null;
  requested_email: string | null;
  decided_email: string | null;
  error: string | null;
  created_at: string;
};

function view(r: Row, url: string | null, me: { userId: string; role: Role }): ProposalView {
  const expired = r.status === "proposed" && Date.now() - new Date(r.created_at).getTime() > 24 * 3600 * 1000;
  return {
    id: r.id,
    action: r.action,
    label: labelOf(r.action),
    title: r.draft?.title ?? null,
    lines: r.status === "proposed" ? (r.draft?.lines ?? []) : [],
    status: expired ? "expired" : r.status,
    requested_email: r.requested_email,
    decided_email: r.decided_email,
    error: r.error,
    link: url && r.record_id ? `${url}/odoo/${r.model}/${r.record_id}` : null,
    canDecide: !expired && r.status === "proposed" && (r.requested_by === me.userId || me.role === "owner" || me.role === "admin"),
  };
}

// Draft cards for a chat, read with the service role after the caller checked membership; people
// who are neither the requester nor an owner/admin see the card without the draft's details.
export async function proposalViews(tenantId: string, ids: string[], me: { userId: string; role: Role }) {
  if (!ids.length) return [];
  const { admin, source } = await loadContext(tenantId);
  const { data } = await admin.from("odoo_actions").select("*").eq("tenant_id", tenantId).in("id", ids.slice(0, 50)).returns<Row[]>();
  return (data ?? []).map((r) => {
    const v = view(r, source?.config.url ?? null, me);
    const mayRead = r.requested_by === me.userId || me.role === "owner" || me.role === "admin";
    return mayRead ? v : { ...v, lines: [] };
  });
}

// Confirm → write to Odoo now. Cancel → nothing is written.
export async function decideChange(tenantId: string, id: string, me: Actor, confirm: boolean): Promise<ProposalView> {
  const { admin, source } = await loadContext(tenantId);
  const { data: row } = await admin.from("odoo_actions").select("*").eq("tenant_id", tenantId).eq("id", id).maybeSingle<Row>();
  if (!row) throw new Error("This draft no longer exists.");
  const current = view(row, source?.config.url ?? null, me);
  if (!current.canDecide) {
    if (current.status !== "proposed") return current;
    throw new Error("Only the person who asked, or an owner/admin, can confirm this.");
  }
  const decided = { decided_by: me.userId, decided_email: me.email, decided_at: new Date().toISOString() };
  if (!confirm) {
    await admin.from("odoo_actions").update({ ...decided, status: "cancelled", draft: null }).eq("id", id).eq("status", "proposed");
    return { ...current, status: "cancelled", lines: [], canDecide: false, decided_email: me.email };
  }
  // Claim the draft first so a double click can't write twice.
  const { data: claimed } = await admin.from("odoo_actions").update({ status: "failed", error: "in progress" }).eq("id", id).eq("status", "proposed").select("id");
  if (!claimed?.length) throw new Error("This draft was already decided.");

  let recordId = row.record_id;
  try {
    await guard(tenantId, row.action, null);
    const { odoo } = await writeClient(tenantId);
    const d = row.draft!;
    const stamp = `Done by Genie at the request of ${row.requested_email ?? "a member"}${row.requested_email !== me.email ? `, confirmed by ${me.email}` : ""} (Ask).`;
    const salesperson = await odooUserByEmail(odoo, row.requested_email);
    if (row.action === "create_lead" || row.action === "create_contact") {
      const vals = { ...d.vals, ...(row.action === "create_lead" && salesperson ? { user_id: salesperson } : {}) };
      const ids = await odoo.call<number[] | number>(row.model, "create", { vals_list: [vals] });
      recordId = Array.isArray(ids) ? ids[0] : ids;
      await odoo.call(row.model, "message_post", { ids: [recordId], body: stamp, message_type: "comment", subtype_xmlid: "mail.mt_note" }).catch(() => null);
    } else if (row.action === "add_note") {
      await odoo.call(row.model, "message_post", { ids: [recordId], body: `${d.note}\n\n— ${stamp}`, message_type: "comment", subtype_xmlid: "mail.mt_note" });
    } else if (row.action === "schedule_follow_up") {
      await odoo.call(row.model, "activity_schedule", {
        ids: [recordId],
        act_type_xmlid: "mail.mail_activity_data_todo",
        date_deadline: d.due_date,
        summary: d.summary,
        note: `${d.note ? `${d.note}\n\n` : ""}${stamp}`,
        ...(salesperson ? { user_id: salesperson } : {}),
      });
    } else {
      await odoo.call(row.model, "write", { ids: [recordId], vals: d.vals });
      await odoo.call(row.model, "message_post", { ids: [recordId], body: stamp, message_type: "comment", subtype_xmlid: "mail.mt_note" }).catch(() => null);
    }
    await admin.from("odoo_actions").update({ ...decided, status: "done", error: null, record_id: recordId, draft: null }).eq("id", id);
    return { ...current, status: "done", lines: [], canDecide: false, decided_email: me.email, error: null, link: source?.config.url && recordId ? `${source.config.url}/odoo/${row.model}/${recordId}` : null };
  } catch (e) {
    const msg = (e instanceof Error ? e.message : String(e)).slice(0, 500);
    await admin.from("odoo_actions").update({ ...decided, status: "failed", error: msg, draft: null }).eq("id", id);
    return { ...current, status: "failed", lines: [], canDecide: false, error: msg };
  }
}

// The Odoo user with the same login email as the member, to set as salesperson / to-do owner.
async function odooUserByEmail(odoo: OdooClient, email: string | null): Promise<number | null> {
  if (!email) return null;
  try {
    const rows = await odoo.call<{ id: number }[]>("res.users", "search_read", { domain: [["login", "=ilike", email]], fields: ["id"], limit: 1 });
    return rows[0]?.id ?? null;
  } catch {
    return null;
  }
}
