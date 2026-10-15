import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { ChevronRight, Plus } from "lucide-react";
import { getUser } from "@/lib/supabase/server";
import { ROLE_LABEL, listMyWorkspaces } from "@/lib/workspaces";

export const metadata: Metadata = { title: "Workspaces" };

export default async function WorkspacesPage() {
  const { user } = await getUser();
  if (!user) redirect("/login");
  const workspaces = await listMyWorkspaces(user.id);
  if (workspaces.length === 0) redirect("/app/new");

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Your workspaces</h1>
        <Link href="/app/new" className="btn-secondary"><Plus size={14} /> New workspace</Link>
      </div>
      <ul className="mt-6 divide-y divide-genie-border rounded-xl border border-genie-border bg-genie-card">
        {workspaces.map((w) => (
          <li key={w.id}>
            <Link href={`/app/${w.slug}`} className="flex items-center justify-between px-5 py-4 hover:bg-genie-bg">
              <div>
                <div className="font-medium">{w.name}</div>
                <div className="text-sm text-genie-muted">{ROLE_LABEL[w.role]} · {w.plan} plan</div>
              </div>
              <ChevronRight size={16} className="text-genie-muted" />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
