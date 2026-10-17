import { redirect } from "next/navigation";
import { HomeTopBar } from "@/components/workspace-shell";
import { getUser } from "@/lib/supabase/server";
import { listMyWorkspaces } from "@/lib/workspaces";

// Outside a workspace (the workspace list, new workspace): the same top bar as inside — logo,
// breadcrumb, account menu.
export default async function HomeLayout({ children }: { children: React.ReactNode }) {
  const { user } = await getUser();
  if (!user) redirect("/login?next=/app");
  const workspaces = await listMyWorkspaces(user.id);
  return (
    <div className="flex min-h-screen flex-col bg-white">
      <HomeTopBar email={user.email ?? ""} crumb="Workspaces" workspaces={workspaces.map((w) => ({ slug: w.slug, name: w.name, role: w.role }))} />
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-8">{children}</main>
    </div>
  );
}
