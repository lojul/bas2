import { redirect } from "next/navigation";
import { ShieldCheck } from "lucide-react";
import { BRAND } from "@/lib/brand";
import { ODOO_MODEL_CHOICES } from "@/lib/odoo/models";
import { createClient, getUser } from "@/lib/supabase/server";
import { canManage, getWorkspace } from "@/lib/workspaces";
import { OdooOff, OdooOffSwitch } from "./forms";

type Source = {
  id: string;
  name: string;
  kind: string;
  status: string;
  last_error: string | null;
  config: { url?: string; db?: string; models?: string[] };
};

// Data sources as on/off cards. Sources are read live (decided 2026-10-16): Genie keeps the
// address and the encrypted key, never a copy of the data.
export async function SourcesSection({ slug }: { slug: string }) {
  const { user } = await getUser();
  if (!user) redirect("/login");
  const workspace = (await getWorkspace(user.id, slug))!;
  if (!canManage(workspace.role)) {
    return <p className="text-sm text-genie-muted">Only owners and admins can see this page.</p>;
  }

  const supabase = await createClient();
  const { data: sources } = await supabase
    .from("sources")
    .select("id, name, kind, status, last_error, config")
    .eq("tenant_id", workspace.id)
    .like("kind", "odoo%")
    .order("created_at")
    .limit(1)
    .returns<Source[]>();
  const odoo = sources?.[0];
  // The listings model is custom to C21's Odoo; other workspaces add custom models under "More Odoo data".
  const choices = ODOO_MODEL_CHOICES.filter((c) => !c.c21Only || slug === "c21");
  const label = (model: string) => ODOO_MODEL_CHOICES.find((c) => c.model === model)?.label ?? model;

  const intro = (
    <p className="text-sm text-genie-muted">
      Read-only and live: when someone asks a question, {BRAND.name}{" "}looks it up in Odoo at that moment. Nothing is copied
      into {BRAND.name}{" "}and nothing in Odoo is changed. Use a dedicated Odoo user that can read the data below.
    </p>
  );

  return (
    <div className="space-y-4">
      <section className="card">
        {odoo ? (
          <div className="space-y-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="font-medium">Odoo</h3>
                <p className="text-sm text-genie-green-deep">On — read live, nothing stored in {BRAND.name}</p>
              </div>
              <OdooOffSwitch slug={slug} sourceId={odoo.id} />
            </div>
            <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]">
              <dt className="text-genie-muted">Address</dt>
              <dd>{odoo.config.url}</dd>
              <dt className="text-genie-muted">{BRAND.name}{" "}can read</dt>
              <dd>{(odoo.config.models ?? []).map(label).join(", ")}</dd>
            </dl>
            {odoo.last_error && <p className="text-sm text-genie-danger">{odoo.last_error}</p>}
            <p className="text-xs text-genie-muted">To change the address, key or what {BRAND.name}{" "}can read, turn Odoo off and on again.</p>
          </div>
        ) : (
          <OdooOff slug={slug} choices={choices} intro={intro} />
        )}
      </section>

      <p className="flex items-start gap-1.5 text-xs text-genie-muted">
        <ShieldCheck size={14} className="mt-px shrink-0" />
        {BRAND.name}{" "}stores only the connection details: the address and the API key (encrypted, can&apos;t be shown again).
        Your records stay in your own system. SQL databases come next.
      </p>
    </div>
  );
}
