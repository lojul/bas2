// The Odoo data Genie reads when the Odoo user may read it (checked when Odoo is switched on).
// `model` is Odoo's internal name; `label` is what people see.
export type OdooModelChoice = { model: string; label: string; hint: string };

export const ODOO_MODEL_CHOICES: OdooModelChoice[] = [
  { model: "res.partner", label: "Contacts", hint: "People and companies (owners, clients, suppliers)" },
  { model: "crm.lead", label: "CRM leads", hint: "Leads and opportunities from the CRM app" },
  { model: "x_c21_listing", label: "Listings", hint: "Property listings (C21's 放盤管理 app)" },
];

// Source kinds for Odoo: JSON-2 (Odoo 19+), the older JSON-RPC, and an MCP-scoped key (read only).
export const ODOO_KINDS = ["odoo_json2", "odoo_xmlrpc", "odoo_mcp"];

// Odoo Online addresses (<name>.odoo.com) use <name> as the database name.
export function guessOdooDb(url: string): string | null {
  try {
    const host = new URL(url).hostname;
    const m = host.match(/^([a-z0-9-]+)\.odoo\.com$/i);
    return m ? m[1] : null;
  } catch {
    return null;
  }
}
