"use server";

import { askAgent } from "@/lib/ai/agent";
import type { ChatTurn } from "@/lib/ai/gateway";
import { getUser } from "@/lib/supabase/server";
import { getWorkspace } from "@/lib/workspaces";

export type AskResult =
  | { ok: true; text: string; model: string; keySource: string; tools: string[] }
  | { ok: false; error: string };

export async function ask(slug: string, history: ChatTurn[]): Promise<AskResult> {
  const { supabase, user } = await getUser();
  if (!user) return { ok: false, error: "Your session has ended. Sign in again." };
  const workspace = await getWorkspace(user.id, slug);
  if (!workspace) return { ok: false, error: "Workspace not found." };
  try {
    const answer = await askAgent(supabase, workspace, user.id, Array.isArray(history) ? history : []);
    return { ok: true, text: answer.text, model: answer.model, keySource: answer.keySource, tools: answer.toolCalls };
  } catch (e) {
    console.error("ask failed", e);
    return { ok: false, error: e instanceof Error ? e.message : "Something went wrong." };
  }
}
