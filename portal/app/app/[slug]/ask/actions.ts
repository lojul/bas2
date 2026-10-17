"use server";

import { revalidatePath } from "next/cache";
import { askAgent } from "@/lib/ai/agent";
import type { ChatTurn } from "@/lib/ai/gateway";
import { createAdminClient } from "@/lib/supabase/admin";
import { getUser } from "@/lib/supabase/server";
import { getWorkspace } from "@/lib/workspaces";

// Saved chats (decided 2026-10-17): kept 90 days after the last message, deletable by their creator
// (or an owner/admin). Team chats: every member reads and posts; Genie answers when @Genie is
// mentioned. Private chats: only the creator; Genie answers every message.

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  author_id: string | null;
  author_email: string | null;
  content: string;
  meta: { model?: string; key_source?: string; tools?: string[]; error?: boolean };
  created_at: string;
};

const MENTION = /@genie\b/i;
const MAX_HISTORY = 20;

async function context(slug: string) {
  const { supabase, user } = await getUser();
  if (!user) throw new Error("Your session has ended. Sign in again.");
  const workspace = await getWorkspace(user.id, slug);
  if (!workspace) throw new Error("Workspace not found.");
  return { supabase, user, workspace };
}

export async function createChat(slug: string, title: string, visibility: "team" | "private"): Promise<{ ok: true; id: string } | { ok: false; error: string }> {
  try {
    const { supabase, user, workspace } = await context(slug);
    const clean = title.replace(/\s+/g, " ").trim().slice(0, 120) || "New chat";
    const { data, error } = await supabase
      .from("chats")
      .insert({ tenant_id: workspace.id, title: clean, visibility: visibility === "team" ? "team" : "private", created_by: user.id })
      .select("id")
      .single();
    if (error) return { ok: false, error: error.message };
    revalidatePath(`/app/${slug}/ask`);
    return { ok: true, id: data.id };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

export async function deleteChat(slug: string, chatId: string): Promise<{ ok: boolean; error?: string }> {
  const { supabase } = await context(slug);
  const { error, count } = await supabase.from("chats").delete({ count: "exact" }).eq("id", chatId);
  if (error) return { ok: false, error: error.message };
  if (!count) return { ok: false, error: "Only the person who started this chat, or an owner/admin, can delete it." };
  revalidatePath(`/app/${slug}/ask`);
  return { ok: true };
}

// Posts a message; asks Genie when the chat is private or the message mentions @Genie.
export async function postMessage(
  slug: string,
  chatId: string,
  text: string,
): Promise<{ ok: true; mine: ChatMessage; answer: ChatMessage | null } | { ok: false; error: string }> {
  const content = text.trim().slice(0, 4000);
  if (!content) return { ok: false, error: "Type a message first." };
  try {
    const { supabase, user, workspace } = await context(slug);
    const { data: chat } = await supabase.from("chats").select("id, visibility").eq("id", chatId).eq("tenant_id", workspace.id).maybeSingle();
    if (!chat) return { ok: false, error: "This chat no longer exists." };

    const { data: mine, error } = await supabase
      .from("chat_messages")
      .insert({ chat_id: chatId, tenant_id: workspace.id, role: "user", author_id: user.id, author_email: user.email, content })
      .select("*")
      .single<ChatMessage>();
    if (error || !mine) return { ok: false, error: error?.message ?? "Could not send." };

    const askGenie = chat.visibility === "private" || MENTION.test(content);
    if (!askGenie) return { ok: true, mine, answer: null };

    // The conversation so far; in team chats each person's message says who wrote it.
    const { data: rows } = await supabase
      .from("chat_messages")
      .select("role, author_email, content")
      .eq("chat_id", chatId)
      .order("created_at", { ascending: false })
      .limit(MAX_HISTORY);
    const history: ChatTurn[] = (rows ?? [])
      .reverse()
      .map((m) => ({
        role: m.role as "user" | "assistant",
        content:
          m.role === "user" && chat.visibility === "team"
            ? `${m.author_email ?? "Someone"}: ${m.content.replace(MENTION, "Genie")}`
            : m.content,
      }));

    let answerText: string;
    let meta: ChatMessage["meta"];
    try {
      const result = await askAgent(supabase, { id: workspace.id, name: workspace.name }, user.id, history);
      answerText = result.text || "(no answer)";
      meta = { model: result.model, key_source: result.keySource, tools: [...new Set(result.toolCalls)] };
    } catch (e) {
      answerText = `Sorry — I couldn't answer that: ${e instanceof Error ? e.message : String(e)}`;
      meta = { error: true };
    }
    // Genie's answer is written by the server (members can only post their own messages).
    const { data: answer } = await createAdminClient()
      .from("chat_messages")
      .insert({ chat_id: chatId, tenant_id: workspace.id, role: "assistant", content: answerText.slice(0, 20000), meta })
      .select("*")
      .single<ChatMessage>();
    return { ok: true, mine, answer: answer ?? null };
  } catch (e) {
    console.error("chat post failed", e);
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}
