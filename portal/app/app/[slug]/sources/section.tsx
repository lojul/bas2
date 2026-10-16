import { redirect } from "next/navigation";
import { ShieldCheck } from "lucide-react";
import { BRAND } from "@/lib/brand";
import { ODOO_MODEL_CHOICES } from "@/lib/odoo/models";
import { createClient, getUser } from "@/lib/supabase/server";
import { canManage, getWorkspace } from "@/lib/workspaces";
import { OdooOff, OffSwitch, SearchOff, type SearchDefaults } from "./forms";

type Source = {
  id: string;
  name: string;
  kind: string;
  status: string;
  last_error: string | null;
  config: { url?: string; db?: string; models?: string[]; endpoint?: string; index?: string };
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
    .in("kind", ["odoo_json2", "odoo_xmlrpc", "azure_search"])
    .order("created_at")
    .returns<Source[]>();
  const odoo = sources?.find((s) => s.kind.startsWith("odoo"));
  const index = sources?.find((s) => s.kind === "azure_search");
  // C21's existing index on its own Azure (the SharePoint building folders, proposals and listings).
  const searchDefaults: SearchDefaults =
    slug === "c21"
      ? { endpoint: "https://c21net-bas-srch-ea-prod.search.windows.net", index: "properties-index", name: "C21 documents", semantic: "default", vectorField: "contentVector" }
      : { endpoint: "", index: "", name: "Documents", semantic: "default", vectorField: "" };
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
              <OffSwitch slug={slug} sourceId={odoo.id} />
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

      <section className="card">
        {index ? (
          <div className="space-y-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="font-medium">Document search index</h3>
                <p className="text-sm text-genie-green-deep">On — searched live, nothing stored in {BRAND.name}</p>
              </div>
              <OffSwitch slug={slug} sourceId={index.id} />
            </div>
            <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]">
              <dt className="text-genie-muted">Name</dt>
              <dd>{index.name}</dd>
              <dt className="text-genie-muted">Index</dt>
              <dd>{index.config.index} · {index.config.endpoint}</dd>
            </dl>
            {index.last_error && <p className="text-sm text-genie-danger">{index.last_error}</p>}
          </div>
        ) : (
          <SearchOff
            slug={slug}
            defaults={searchDefaults}
            intro={
              <p className="text-sm text-genie-muted">
                Your own Azure AI Search index — e.g. documents from SharePoint already indexed there. {BRAND.name}{" "}searches it
                live with a read-only query key; nothing is copied.
              </p>
            }
          />
        )}
      </section>

      <p className="flex items-start gap-1.5 text-xs text-genie-muted">
        <ShieldCheck size={14} className="mt-px shrink-0" />
        {BRAND.name}{" "}stores only the connection details: the address and the API key (encrypted, can&apos;t be shown again).
        Your records and documents stay in your own systems. SQL databases come next.
      </p>
    </div>
  );
}
