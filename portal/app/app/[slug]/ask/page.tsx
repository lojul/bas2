import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { createClient, getUser } from "@/lib/supabase/server";
import { canManage, getWorkspace } from "@/lib/workspaces";
import { SetupStrip, type SetupStep } from "./setup-strip";
import { Chat } from "./chat";

export const metadata: Metadata = { title: "Ask" };
// A question can take several model and tool round trips.
export const maxDuration = 120;

export default async function AskPage({ params, searchParams }: PageProps<"/app/[slug]/ask">) {
  const { slug } = await params;
  const q = (await searchParams).q;
  const { user } = await getUser();
  if (!user) redirect("/login");
  const workspace = await getWorkspace(user.id, slug);
  if (!workspace) redirect("/app");

  // Setup checklist, only for people who can act on it.
  let steps: SetupStep[] | null = null;
  if (canManage(workspace.role)) {
    const supabase = await createClient();
    const count = (q: PromiseLike<{ count: number | null }>) => Promise.resolve(q).then((r) => r.count ?? 0);
    const [members, sources, keys] = await Promise.all([
      count(supabase.from("tenant_members").select("*", { count: "exact", head: true }).eq("tenant_id", workspace.id)),
      count(supabase.from("sources").select("*", { count: "exact", head: true }).eq("tenant_id", workspace.id)),
      count(supabase.from("tenant_secrets").select("id", { count: "exact", head: true }).eq("tenant_id", workspace.id).eq("kind", "ai_key")),
    ]);
    steps = [
      { done: sources > 0, text: "Switch on a data source", href: `/app/${slug}/settings#data-sources` },
      { done: members > 1, text: "Invite your colleagues", href: `/app/${slug}/members` },
      { done: keys > 0, text: "Add your own AI key (optional)", href: `/app/${slug}/settings#ai-keys` },
    ];
  }

  return (
    <div className="space-y-4">
      {steps && <SetupStrip slug={slug} steps={steps} />}
      <Chat slug={slug} initialQuestion={typeof q === "string" ? q.slice(0, 500) : ""} />
    </div>
  );
}
