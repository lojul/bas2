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
      .select("name, status")
      .eq("tenant_id", workspace.id)
      .order("created_at"),
  ]);
  const source: SourceStatus = sources?.length
    ? { name: sources.map((s) => s.name).join(", "), status: sources.some((s) => s.status === "error") ? "error" : "active" }
    : null;

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
