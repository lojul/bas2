import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { WorkspaceTabs } from "@/components/workspace-tabs";
import { getUser } from "@/lib/supabase/server";
import { ROLE_LABEL, canManage, getWorkspace } from "@/lib/workspaces";

export default async function WorkspaceLayout({ children, params }: LayoutProps<"/app/[slug]">) {
  const { slug } = await params;
  const { user } = await getUser();
  if (!user) redirect("/login");
  const workspace = await getWorkspace(user.id, slug);
  if (!workspace) notFound();

  return (
    <div>
      <Link href="/app" className="text-sm text-genie-muted hover:text-genie-ink">← All workspaces</Link>
      <div className="mt-2 flex items-baseline gap-3">
        <h1 className="text-2xl font-semibold">{workspace.name}</h1>
        <span className="rounded-full bg-genie-accent px-2 py-0.5 text-xs">{ROLE_LABEL[workspace.role]}</span>
      </div>
      <WorkspaceTabs slug={slug} showKeys={canManage(workspace.role)} />
      <div className="mt-6">{children}</div>
    </div>
  );
}
