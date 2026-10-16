import { redirect } from "next/navigation";
import { getUser } from "@/lib/supabase/server";

// Everything under /app needs a signed-in user. Workspace pages get the sidebar layout in
// [slug]/layout.tsx; the workspace list and "new workspace" use (home)/layout.tsx.
export default async function AppLayout({ children }: LayoutProps<"/app">) {
  const { user } = await getUser();
  if (!user) redirect("/login?next=/app");
  return <div className="flex flex-1 flex-col">{children}</div>;
}
