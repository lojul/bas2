import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { BRAND } from "@/lib/brand";
import { getUser } from "@/lib/supabase/server";
import { getWorkspace } from "@/lib/workspaces";
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

  return (
    <div className="space-y-4">
      <p className="text-sm text-genie-muted">
        Ask {BRAND.name}{" "}about {workspace.name}&apos;s data. Answers come only from your workspace&apos;s records and
        documents; the conversation is not saved.
      </p>
      <Chat slug={slug} initialQuestion={typeof q === "string" ? q.slice(0, 500) : ""} />
    </div>
  );
}
