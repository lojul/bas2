import { notFound, redirect } from "next/navigation";
import { WorkspaceShell, type SourceStatus } from "@/components/workspace-shell";
import { createClient, getUser } from "@/lib/supabase/server";
import { getWorkspace, listMyWorkspaces } from "@/lib/workspaces";

export default async function WorkspaceLayout({ children, params }: LayoutProps<"/app/[slug]">) {
  const { slug } = await params;
  const { user } = await getUser();
  if (!user) redirect("/login");
  const workspace = await getWorkspace(user.id, slug);
  if (!workspace) notFound();

  const supabase = await createClient();
  const [workspaces, { data: sources }] = await Promise.all([
    listMyWorkspaces(user.id),
    supabase
      .from("sources")
      .select("name, status, last_synced_at")
      .eq("tenant_id", workspace.id)
      .order("last_synced_at", { ascending: false, nullsFirst: false })
      .limit(1),
  ]);
  const first = sources?.[0];
  const source: SourceStatus = first ? { name: first.name, status: first.status, lastSyncedAt: first.last_synced_at } : null;

  return (
    <WorkspaceShell
      workspace={{ slug: workspace.slug, name: workspace.name, role: workspace.role }}
      workspaces={workspaces.map((w) => ({ slug: w.slug, name: w.name, role: w.role }))}
      email={user.email ?? ""}
      source={source}
    >
      {children}
    </WorkspaceShell>
  );
}
