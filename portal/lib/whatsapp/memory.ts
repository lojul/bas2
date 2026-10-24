import "server-only";
import type { ChatTurn } from "@/lib/ai/gateway";
import { createAdminClient } from "@/lib/supabase/admin";

// A member's recent WhatsApp conversation (table whatsapp_turns), so Genie can ask for a missing
// detail and use the reply. Only the last 30 minutes are used; a database job deletes older rows.

const WINDOW_MINUTES = 30;
const MAX_TURNS = 12;

type Turn = { role: "user" | "assistant"; content: string; proposals: string[] };

export async function recentTurns(tenantId: string, userId: string): Promise<Turn[]> {
  const since = new Date(Date.now() - WINDOW_MINUTES * 60_000).toISOString();
  const { data, error } = await createAdminClient()
    .from("whatsapp_turns")
    .select("role, content, proposals")
    .eq("tenant_id", tenantId)
    .eq("user_id", userId)
    .gte("created_at", since)
    .order("created_at", { ascending: false })
    .limit(MAX_TURNS)
    .returns<Turn[]>();
  if (error) console.error("whatsapp memory read failed", error.message);
  return (data ?? []).reverse();
}

export const asHistory = (turns: Turn[]): ChatTurn[] => turns.map((t) => ({ role: t.role, content: t.content }));

// Drafts from Genie's latest answer: what a YES / NO reply refers to.
export const lastProposals = (turns: Turn[]) => [...turns].reverse().find((t) => t.role === "assistant")?.proposals ?? [];

export async function saveTurns(tenantId: string, userId: string, question: string, answer: string, proposals: string[] = []) {
  const { error } = await createAdminClient()
    .from("whatsapp_turns")
    .insert([
      { tenant_id: tenantId, user_id: userId, role: "user", content: question.slice(0, 4000), proposals: [] },
      { tenant_id: tenantId, user_id: userId, role: "assistant", content: answer.slice(0, 4000), proposals },
    ]);
  if (error) console.error("whatsapp memory write failed", error.message);
}
