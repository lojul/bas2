import { redirect } from "next/navigation";
import { CHANGE_ACTIONS, type ChangeAction } from "@/lib/odoo/changes";
import { ODOO_KINDS } from "@/lib/odoo/models";
import { createClient, getUser } from "@/lib/supabase/server";
import { canManage, getWorkspace } from "@/lib/workspaces";

type Row = {
  id: string;
  action: ChangeAction;
  model: string;
  record_id: number | null;
  status: "proposed" | "done" | "cancelled" | "failed" | "expired";
  error: string | null;
  requested_email: string | null;
  decided_email: string | null;
  created_at: string;
};

const STATUS: Record<Row["status"], { text: string; cls: string }> = {
  proposed: { text: "Waiting for Confirm", cls: "text-amber-700" },
  done: { text: "Saved in Odoo", cls: "text-genie-green" },
  cancelled: { text: "Cancelled", cls: "text-genie-muted" },
  expired: { text: "Expired", cls: "text-genie-muted" },
  failed: { text: "Failed", cls: "text-genie-danger" },
};

// Settings → Activity: every change Genie prepared or made in Odoo (who, what, when, which record).
// Kept one year; no copy of the record's contents.
export async function ActivitySection({ slug }: { slug: string }) {
  const { user } = await getUser();
  if (!user) redirect("/login");
  const workspace = (await getWorkspace(user.id, slug))!;
  if (!canManage(workspace.role)) return <p className="text-sm text-genie-muted">Only owners and admins can see this page.</p>;

  const supabase = await createClient();
  const [{ data: rows }, { data: source }] = await Promise.all([
    supabase
      .from("odoo_actions")
      .select("id, action, model, record_id, status, error, requested_email, decided_email, created_at")
      .eq("tenant_id", workspace.id)
      .order("created_at", { ascending: false })
      .limit(200)
      .returns<Row[]>(),
    supabase.from("sources").select("config").eq("tenant_id", workspace.id).in("kind", ODOO_KINDS).limit(1).maybeSingle<{ config: { url?: string } }>(),
  ]);
  const url = source?.config.url;
  const label = (a: ChangeAction) => CHANGE_ACTIONS.find((x) => x.id === a)?.label ?? a;

  if (!rows?.length) return <p className="text-sm text-genie-muted">No changes in Odoo yet.</p>;
  return (
    <div className="overflow-x-auto rounded-lg border border-genie-border">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-genie-border bg-genie-accent/50 text-genie-muted">
          <tr>
            <th className="px-4 py-2.5 font-normal">When</th>
            <th className="px-4 py-2.5 font-normal">Asked by</th>
            <th className="px-4 py-2.5 font-normal">Change</th>
            <th className="px-4 py-2.5 font-normal">Result</th>
            <th className="px-4 py-2.5 font-normal">Odoo record</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-genie-border">
          {rows.map((r) => (
            <tr key={r.id} className="align-top">
              <td className="whitespace-nowrap px-4 py-2.5">{new Date(r.created_at).toLocaleString("en-GB", { timeZone: "Asia/Hong_Kong", dateStyle: "short", timeStyle: "short" })}</td>
              <td className="px-4 py-2.5">
                {r.requested_email}
                {r.decided_email && r.decided_email !== r.requested_email && <div className="text-xs text-genie-muted">confirmed by {r.decided_email}</div>}
              </td>
              <td className="px-4 py-2.5">{label(r.action)}</td>
              <td className={`px-4 py-2.5 ${STATUS[r.status].cls}`}>
                {STATUS[r.status].text}
                {r.status === "failed" && r.error && <div className="max-w-xs text-xs">{r.error}</div>}
              </td>
              <td className="px-4 py-2.5">
                {url && r.record_id ? (
                  <a href={`${url}/odoo/${r.model}/${r.record_id}`} target="_blank" rel="noreferrer" className="underline underline-offset-2">
                    {r.model} #{r.record_id}
                  </a>
                ) : (
                  <span className="text-genie-muted">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
