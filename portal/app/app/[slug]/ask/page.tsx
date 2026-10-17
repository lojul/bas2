import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { createClient, getUser } from "@/lib/supabase/server";
import { proposalViews } from "@/lib/odoo/changes";
import { canManage, getWorkspace } from "@/lib/workspaces";
import { SetupStrip, type SetupStep } from "./setup-strip";
import type { ChatMessage } from "./actions";
import { type ChatSummary, ChatRoom, type Suggestion } from "./chat-room";

export const metadata: Metadata = { title: "Ask" };
// A question can take several model and tool round trips.
export const maxDuration = 120;

export default async function AskPage({ params, searchParams }: PageProps<"/app/[slug]/ask">) {
  const { slug } = await params;
  const { q, chat: chatParam } = await searchParams;
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
      { done: sources > 0, text: "Switch on a data source", href: `/app/${slug}/settings?tab=data-sources` },
      { done: members > 1, text: "Invite your colleagues", href: `/app/${slug}/members` },
      { done: keys > 0, text: "Add your own AI key (optional)", href: `/app/${slug}/settings?tab=ai-keys` },
    ];
  }

  // Suggestion cards that fit the switched-on sources.
  const supabaseForSources = await createClient();
  const { data: kinds } = await supabaseForSources.from("sources").select("kind").eq("tenant_id", workspace.id);
  const hasOdoo = kinds?.some((k) => k.kind.startsWith("odoo")) ?? false;
  const hasDocs = kinds?.some((k) => k.kind === "azure_search") ?? false;
  const suggestions: Suggestion[] = [
    ...(hasOdoo ? [{ kind: "contact" as const, title: "Find a contact", prompt: "Find the phone number of the owner Chan Tai Man" }] : []),
    ...(hasOdoo ? [{ kind: "listing" as const, title: "Search listings", prompt: "3-bedroom flats for rent in Taikoo Shing" }] : []),
    ...(hasDocs ? [{ kind: "document" as const, title: "Search documents", prompt: "What do we have at SOHO East in Sai Wan Ho?" }] : []),
    { kind: "idea" as const, title: "Get started", prompt: "What data can you see?" },
  ].slice(0, 3);

  // Saved chats this person can see (team chats + their own private ones; row-level security), and the
  // open one with its messages.
  const { data: chatRows } = await supabaseForSources
    .from("chats")
    .select("id, title, visibility, created_by")
    .eq("tenant_id", workspace.id)
    .order("last_message_at", { ascending: false })
    .limit(100)
    .returns<ChatSummary[]>();
  const chats = chatRows ?? [];
  const chat = typeof chatParam === "string" ? (chats.find((c) => c.id === chatParam) ?? null) : null;
  let messages: ChatMessage[] = [];
  if (chat) {
    const { data } = await supabaseForSources
      .from("chat_messages")
      .select("*")
      .eq("chat_id", chat.id)
      .order("created_at")
      .limit(500)
      .returns<ChatMessage[]>();
    messages = data ?? [];
  }
  const proposalIds = messages.flatMap((m) => m.meta?.proposals ?? []);
  const proposals = proposalIds.length ? await proposalViews(workspace.id, proposalIds, { userId: user.id, role: workspace.role }) : [];
  const canDelete = !!chat && (chat.created_by === user.id || canManage(workspace.role));

  return (
    <div className="space-y-4">
      {steps && !chat && <SetupStrip slug={slug} steps={steps} />}
      <ChatRoom
        key={chat?.id ?? "new"}
        slug={slug}
        me={{ id: user.id, email: user.email ?? "" }}
        chat={chat}
        initialMessages={messages}
        canDelete={canDelete}
        initialProposals={proposals}
        greeting="Hi, how can I help?"
        suggestions={suggestions}
        initialQuestion={typeof q === "string" ? q.slice(0, 500) : ""}
      />
    </div>
  );
}
