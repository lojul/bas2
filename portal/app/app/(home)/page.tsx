import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowRight, Plus } from "lucide-react";
import { createClient, getUser } from "@/lib/supabase/server";
import { ROLE_LABEL, listMyWorkspaces } from "@/lib/workspaces";

export const metadata: Metadata = { title: "Workspaces" };

// The level above the workspaces: pick a company. Someone in exactly one workspace goes straight in
// (unless they asked for this list with ?all=1, e.g. from "All workspaces").
export default async function WorkspacesPage({ searchParams }: PageProps<"/app">) {
  const { all } = await searchParams;
  const { user } = await getUser();
  if (!user) redirect("/login");
  const workspaces = await listMyWorkspaces(user.id);
  if (workspaces.length === 0) redirect("/app/new");
  if (workspaces.length === 1 && !all) redirect(`/app/${workspaces[0].slug}`);

  const supabase = await createClient();
  const { data: sources } = await supabase.from("sources").select("tenant_id, name").in("tenant_id", workspaces.map((w) => w.id));

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Your workspaces</h1>
          <p className="mt-1 text-sm text-genie-muted">One workspace per company. Pick one to ask about its data.</p>
        </div>
        <Link href="/app/new" className="btn-secondary">
          <Plus size={14} /> New workspace
        </Link>
      </div>
      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        {workspaces.map((w) => {
          const names = (sources ?? []).filter((s) => s.tenant_id === w.id).map((s) => s.name);
          return (
            <Link key={w.id} href={`/app/${w.slug}`} className="card flex flex-col gap-3 hover:bg-genie-accent/40">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-base font-semibold">{w.name}</div>
                  <div className="text-sm text-genie-muted">
                    {ROLE_LABEL[w.role]} · <span className="capitalize">{w.plan}</span> plan
                  </div>
                </div>
                <ArrowRight size={16} className="mt-1 text-genie-muted" />
              </div>
              <div className="flex items-center gap-2 text-xs text-genie-muted">
                <span className={`h-2 w-2 rounded-full ${names.length ? "bg-genie-green" : "bg-gray-300"}`} />
                {names.length ? `${names.join(", ")} · read live` : "No data source switched on"}
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
