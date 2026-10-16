import { redirect } from "next/navigation";
import { Database, Lock } from "lucide-react";
import { BRAND } from "@/lib/brand";
import { createClient, getUser } from "@/lib/supabase/server";
import { canManage, getWorkspace } from "@/lib/workspaces";
import { ODOO_MODEL_CHOICES } from "@/lib/sync/models";
import { removeSource } from "./actions";
import { OdooForm, SyncButton } from "./forms";


type Source = {
  id: string;
  name: string;
  kind: string;
  status: string;
  last_synced_at: string | null;
  last_error: string | null;
  config: { url?: string; db?: string; models?: string[] };
};

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
    .select("id, name, kind, status, last_synced_at, last_error, config")
    .eq("tenant_id", workspace.id)
    .order("name")
    .returns<Source[]>();
  const { count } = await supabase
    .from("records")
    .select("id", { count: "exact", head: true })
    .eq("tenant_id", workspace.id)
    .is("deleted_at", null);
  // The listings model is custom to C21's Odoo; other workspaces add custom models under "More Odoo data".
  const choices = ODOO_MODEL_CHOICES.filter((c) => !c.c21Only || slug === "c21");

  return (
    <div className="space-y-6">
      <section>
        <h2 className="mb-2 font-medium">Connected sources</h2>
        {sources && sources.length > 0 ? (
          <ul className="divide-y divide-genie-border rounded-xl border border-genie-border bg-genie-card">
            {sources.map((s) => (
              <li key={s.id} className="space-y-2 px-5 py-4 text-sm">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3">
                    <Database size={16} className="mt-0.5 text-genie-green" />
                    <div>
                      <div className="font-medium">
                        {s.name} <span className="font-normal text-genie-muted">· {s.kind} · {s.status}</span>
                      </div>
                      <div className="text-xs text-genie-muted">
                        {s.config.url ? `${s.config.url} (${s.config.db}) · ` : ""}
                        {s.config.models?.length ? `${s.config.models.join(", ")} · ` : ""}
                        {s.last_synced_at ? `last sync ${new Date(s.last_synced_at).toLocaleString()}` : "not synced yet"}
                      </div>
                      {s.last_error && <div className="mt-1 text-xs text-genie-danger">{s.last_error}</div>}
                    </div>
                  </div>
                  {s.kind.startsWith("odoo") && (
                    <form action={removeSource}>
                      <input type="hidden" name="slug" value={slug} />
                      <input type="hidden" name="source_id" value={s.id} />
                      <button type="submit" className="btn-danger">Remove</button>
                    </form>
                  )}
                </div>
                {s.kind.startsWith("odoo") && <SyncButton slug={slug} sourceId={s.id} />}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-genie-muted">No data sources yet.</p>
        )}
        <p className="mt-2 text-xs text-genie-muted">{count ?? 0} records in {BRAND.name}{" "}for this workspace.</p>
      </section>

      <section className="card">
        <h2 className="font-medium">Connect Odoo</h2>
        <p className="mb-4 mt-1 text-sm text-genie-muted">
          Read-only: {BRAND.name}{" "}copies the records it can see and never changes anything in Odoo. Use a dedicated
          Odoo user with read access to the data below, and create its API key under Odoo → Preferences → Account
          Security → New API Key.
        </p>
        <OdooForm slug={slug} choices={choices} />
        <p className="mt-4 flex items-center gap-1.5 text-xs text-genie-muted">
          <Lock size={12} /> The API key is encrypted in Supabase Vault and can&apos;t be shown again.
        </p>
      </section>
    </div>
  );
}
