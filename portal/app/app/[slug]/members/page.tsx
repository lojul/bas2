import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { createClient, getUser } from "@/lib/supabase/server";
import { type Role, ROLE_LABEL, canManage, getWorkspace } from "@/lib/workspaces";
import { revokeInvitation } from "./actions";
import { InviteForm, RenewInvite } from "./invite-form";
import { MemberRow } from "./member-row";

export const metadata: Metadata = { title: "Members" };

type Member = { user_id: string; email: string; role: Role; joined_at: string };
type Invitation = { id: string; email: string; role: Role; expires_at: string; accepted_at: string | null; created_at: string };

// Pending = not accepted and not expired; history = accepted or expired (kept, so nothing vanishes).
function splitInvitations(all: Invitation[]) {
  const now = Date.now();
  const live = (i: Invitation) => !i.accepted_at && new Date(i.expires_at).getTime() > now;
  return { pending: all.filter(live), history: all.filter((i) => !live(i)) };
}

export default async function MembersPage({ params }: PageProps<"/app/[slug]/members">) {
  const { slug } = await params;
  const { user } = await getUser();
  if (!user) redirect("/login");
  const workspace = (await getWorkspace(user.id, slug))!;
  const manage = canManage(workspace.role);

  const supabase = await createClient();
  const { data: memberRows } = await supabase.rpc("list_tenant_members", { p_tenant_id: workspace.id });
  const members = (memberRows ?? []) as Member[];
  const { data: invitations } = manage
    ? await supabase
        .from("invitations")
        .select("id, email, role, expires_at, accepted_at, created_at")
        .eq("tenant_id", workspace.id)
        .order("created_at", { ascending: false })
        .limit(100)
        .returns<Invitation[]>()
    : { data: [] as Invitation[] };
  const { pending, history } = splitInvitations(invitations ?? []);

  return (
    <div className="space-y-6">
      <p className="text-sm text-genie-muted">
        {members.length} {members.length === 1 ? "member" : "members"} · <span className="capitalize">{workspace.plan}</span> plan
        {workspace.document_addon ? " + documents" : ""}
      </p>
      {manage && (
        <section className="card">
          <h2 className="font-medium">Invite someone</h2>
          <p className="mb-4 mt-1 text-sm text-genie-muted">
            Admins manage members, sources and keys. Members can ask questions and upload documents. Viewers can only ask.
          </p>
          <InviteForm slug={slug} />
        </section>
      )}

      <section>
        <h2 className="mb-2 font-medium">Members ({members.length})</h2>
        <ul className="divide-y divide-genie-border rounded-xl border border-genie-border bg-genie-card">
          {members.map((m) => (
            <MemberRow key={m.user_id} slug={slug} member={m} isSelf={m.user_id === user.id} myRole={workspace.role} />
          ))}
        </ul>
      </section>

      {manage && pending.length > 0 && (
        <section>
          <h2 className="mb-2 font-medium">Pending invitations</h2>
          <ul className="divide-y divide-genie-border rounded-xl border border-genie-border bg-genie-card">
            {pending.map((inv) => (
              <li key={inv.id} className="flex flex-wrap items-start justify-between gap-3 px-5 py-3 text-sm">
                <div>
                  {inv.email} <span className="text-genie-muted">· {ROLE_LABEL[inv.role]}</span>
                  <div className="text-xs text-genie-muted">Link valid until {new Date(inv.expires_at).toLocaleDateString()}</div>
                </div>
                <div className="flex items-start gap-2">
                  <RenewInvite slug={slug} id={inv.id} />
                  <form action={revokeInvitation}>
                    <input type="hidden" name="slug" value={slug} />
                    <input type="hidden" name="id" value={inv.id} />
                    <button type="submit" className="btn-danger mt-1">Revoke</button>
                  </form>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {manage && history.length > 0 && (
        <section>
          <h2 className="mb-2 font-medium">Invitation history</h2>
          <ul className="divide-y divide-genie-border rounded-xl border border-genie-border bg-genie-card">
            {history.map((inv) => (
              <li key={inv.id} className="flex flex-wrap items-start justify-between gap-3 px-5 py-3 text-sm">
                <div>
                  {inv.email} <span className="text-genie-muted">· {ROLE_LABEL[inv.role]}</span>
                  <div className="text-xs text-genie-muted">
                    Invited {new Date(inv.created_at).toLocaleDateString()} ·{" "}
                    {inv.accepted_at ? (
                      <span className="text-genie-green">accepted {new Date(inv.accepted_at).toLocaleDateString()}</span>
                    ) : (
                      "expired"
                    )}
                  </div>
                </div>
                {!inv.accepted_at && <RenewInvite slug={slug} id={inv.id} />}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
