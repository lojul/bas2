import "server-only";
import { createHmac, timingSafeEqual } from "node:crypto";
import { createAdminClient } from "@/lib/supabase/admin";

// Genie in Slack: a workspace connects its own Slack app (bot token + signing secret, kept in Vault)
// and points the app's Event Subscriptions at /api/slack/<workspace slug>/events. Messages are read
// from Slack and answered there; Genie stores nothing but the keys and the usage counts.

import { SLACK_SIGNING_SECRET, SLACK_TOKEN_SECRET } from "./names";

export { SLACK_SIGNING_SECRET, SLACK_TOKEN_SECRET };

// enabled: the Slack switch in Settings → Channels. Off = the bot doesn't answer (keys are kept).
export type SlackSettings = {
  team?: string;
  team_id?: string;
  bot_user_id?: string;
  bot_name?: string;
  connected_at?: string;
  enabled?: boolean;
};

export function verifySlackSignature(signingSecret: string, timestamp: string | null, signature: string | null, rawBody: string) {
  if (!timestamp || !signature) return false;
  // Reject replays older than 5 minutes.
  if (Math.abs(Date.now() / 1000 - Number(timestamp)) > 300) return false;
  const expected = `v0=${createHmac("sha256", signingSecret).update(`v0:${timestamp}:${rawBody}`).digest("hex")}`;
  const a = Buffer.from(expected);
  const b = Buffer.from(signature);
  return a.length === b.length && timingSafeEqual(a, b);
}

export async function slackApi<T = Record<string, unknown>>(token: string, method: string, body: Record<string, unknown>): Promise<T & { ok: boolean; error?: string }> {
  const res = await fetch(`https://slack.com/api/${method}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  return (await res.json()) as T & { ok: boolean; error?: string };
}

// Workspace + its Slack keys, by slug (service role: the request comes from Slack, not a user).
export async function slackWorkspace(slug: string) {
  const admin = createAdminClient();
  const { data: tenant } = await admin
    .from("tenants")
    .select("id, name, status, settings")
    .eq("slug", slug)
    .maybeSingle<{ id: string; name: string; status: string; settings: { channels?: { slack?: SlackSettings } } | null }>();
  if (!tenant || tenant.status !== "active") return null;
  const secret = async (name: string) => {
    const { data } = await admin.rpc("get_tenant_secret", { p_tenant_id: tenant.id, p_name: name });
    return (data as string | null) ?? null;
  };
  const [token, signingSecret] = await Promise.all([secret(SLACK_TOKEN_SECRET), secret(SLACK_SIGNING_SECRET)]);
  if (!token || !signingSecret) return null;
  return { id: tenant.id, name: tenant.name, slack: tenant.settings?.channels?.slack ?? {}, token, signingSecret };
}

// Markdown (as the model writes it) → Slack mrkdwn.
export function toSlackMrkdwn(md: string): string {
  return md
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, "<$2|$1>")
    .replace(/^#{1,6}\s+(.+)$/gm, "*$1*")
    .replace(/\*\*([^*]+)\*\*/g, "*$1*")
    .replace(/__([^_]+)__/g, "*$1*")
    .replace(/^(\s*)[-*]\s+/gm, "$1• ");
}

// Strip "<@U123>" mentions of the bot from the question.
export const stripMentions = (text: string) => text.replace(/<@[A-Z0-9]+>/g, "").trim();
