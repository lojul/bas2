import { notFound, redirect } from "next/navigation";
import { type SidebarChat, type StatusItem, WorkspaceShell } from "@/components/workspace-shell";
import { createClient, getUser } from "@/lib/supabase/server";
import { getWorkspace, listMyWorkspaces } from "@/lib/workspaces";

export default async function WorkspaceLayout({ children, params }: LayoutProps<"/app/[slug]">) {
  const { slug } = await params;
  const { user } = await getUser();
  if (!user) redirect("/login");
  const workspace = await getWorkspace(user.id, slug);
  if (!workspace) notFound();

  const supabase = await createClient();
  const [workspaces, { data: sourceRows }, { data: tenant }, { data: chatRows }] = await Promise.all([
    listMyWorkspaces(user.id),
    supabase.from("sources").select("name, status").eq("tenant_id", workspace.id).order("created_at"),
    supabase
      .from("tenants")
      .select("settings")
      .eq("id", workspace.id)
      .single<{ settings: { channels?: { slack?: { enabled?: boolean }; whatsapp?: { enabled?: boolean } } } | null }>(),
    // Saved chats this person can see (team + own private), newest first, for the sidebar under Ask.
    supabase
      .from("chats")
      .select("id, title, visibility")
      .eq("tenant_id", workspace.id)
      .order("last_message_at", { ascending: false })
      .limit(30)
      .returns<SidebarChat[]>(),
  ]);
  const sources: StatusItem[] = (sourceRows ?? []).map((s) => ({ name: s.name, state: s.status === "error" ? "error" : "on" }));
  const ch = tenant?.settings?.channels ?? {};
  const channels: StatusItem[] = [
    ...(ch.slack ? [{ name: "Slack", state: ch.slack.enabled === false ? "off" : "on" } as StatusItem] : []),
    ...(ch.whatsapp ? [{ name: "WhatsApp", state: ch.whatsapp.enabled === false ? "off" : "on" } as StatusItem] : []),
  ];

  return (
    <WorkspaceShell
      workspace={{ slug: workspace.slug, name: workspace.name, role: workspace.role }}
      workspaces={workspaces.map((w) => ({ slug: w.slug, name: w.name, role: w.role }))}
      email={user.email ?? ""}
      sources={sources}
      channels={channels}
      chats={chatRows ?? []}
    >
      {children}
    </WorkspaceShell>
  );
}
