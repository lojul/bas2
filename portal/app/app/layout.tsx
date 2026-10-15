import { redirect } from "next/navigation";
import { LogOut } from "lucide-react";
import { Logo } from "@/components/logo";
import { getUser } from "@/lib/supabase/server";

export default async function AppLayout({ children }: LayoutProps<"/app">) {
  const { user } = await getUser();
  if (!user) redirect("/login?next=/app");

  return (
    <div className="flex flex-1 flex-col">
      <header className="border-b border-genie-border bg-genie-card">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-6 py-3">
          <Logo href="/app" />
          <div className="flex items-center gap-3 text-sm">
            <span className="hidden text-genie-muted sm:inline">{user.email}</span>
            <form action="/auth/signout" method="post">
              <button type="submit" className="btn-secondary px-3 py-1.5" title="Sign out">
                <LogOut size={14} /> Sign out
              </button>
            </form>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-8">{children}</main>
    </div>
  );
}
