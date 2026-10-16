// What a new Odoo source can copy, in plain words. `model` is Odoo's internal name.
export type OdooModelChoice = { model: string; label: string; hint: string; c21Only?: boolean };

export const ODOO_MODEL_CHOICES: OdooModelChoice[] = [
  { model: "res.partner", label: "Contacts", hint: "People and companies (owners, clients, suppliers)" },
  { model: "crm.lead", label: "CRM leads", hint: "Leads and opportunities from the CRM app" },
  { model: "x_c21_listing", label: "Listings", hint: "C21 property listings (放盤管理)", c21Only: true },
];

// Odoo models Genie may read when none are ticked explicitly.
export const DEFAULT_ODOO_MODELS = "res.partner, crm.lead";

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
