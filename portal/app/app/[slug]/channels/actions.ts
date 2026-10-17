"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import type { FormState } from "@/components/form-message";
import { SLACK_SIGNING_SECRET, SLACK_TOKEN_SECRET, type SlackSettings, slackApi } from "@/lib/slack/slack";
import { TWILIO_TOKEN_SECRET, type WhatsAppSettings, twilioAccount } from "@/lib/whatsapp/twilio";
import { createAdminClient } from "@/lib/supabase/admin";
import { getUser } from "@/lib/supabase/server";
import { canManage, getWorkspace } from "@/lib/workspaces";

async function context(slug: string) {
  const { supabase, user } = await getUser();
  if (!user) redirect("/login");
  const workspace = await getWorkspace(user.id, slug);
  if (!workspace) redirect("/app");
  if (!canManage(workspace.role)) throw new Error("Only owners and admins can manage channels.");
  return { supabase, workspace };
}

type AuthTest = { team?: string; team_id?: string; user?: string; user_id?: string };

async function readSettings(supabase: Awaited<ReturnType<typeof context>>["supabase"], tenantId: string) {
  const { data } = await supabase.from("tenants").select("settings").eq("id", tenantId).single<{ settings: Record<string, unknown> | null }>();
  return data?.settings ?? {};
}

// Save (or edit) the Slack connection: checks the bot token with Slack, keeps both keys in Vault and
// the non-secret details (Slack workspace, bot) in tenants.settings.channels.slack.
export async function connectSlack(_prev: FormState, formData: FormData): Promise<FormState> {
  const slug = String(formData.get("slug"));
  const { supabase, workspace } = await context(slug);
  const editing = formData.get("editing") === "1";
  let token = String(formData.get("bot_token") ?? "").trim();
  const signing = String(formData.get("signing_secret") ?? "").trim();

  if (editing && !token) {
    const { data } = await createAdminClient().rpc("get_tenant_secret", { p_tenant_id: workspace.id, p_name: SLACK_TOKEN_SECRET });
    token = (data as string | null) ?? "";
  }
  if (!token.startsWith("xoxb-")) return { error: "Paste the Bot User OAuth Token (starts with xoxb-)." };
  if (!editing && signing.length < 20) return { error: "Paste the Signing Secret (Slack app → Basic Information)." };

  const auth = await slackApi<AuthTest>(token, "auth.test", {});
  if (!auth.ok) return { error: `Slack refused the token (${auth.error}).` };

  const save = (name: string, value: string) =>
    supabase.rpc("set_tenant_secret", { p_tenant_id: workspace.id, p_name: name, p_kind: "other", p_provider: "slack", p_secret: value });
  if (formData.get("bot_token")) {
    const { error } = await save(SLACK_TOKEN_SECRET, token);
    if (error) return { error: `Could not save the token: ${error.message}` };
  }
  if (signing) {
    const { error } = await save(SLACK_SIGNING_SECRET, signing);
    if (error) return { error: `Could not save the signing secret: ${error.message}` };
  }

  const settings = await readSettings(supabase, workspace.id);
  const channels = (settings.channels as Record<string, unknown> | undefined) ?? {};
  const before = (channels.slack as SlackSettings | undefined) ?? {};
  const slack: SlackSettings = {
    team: auth.team,
    team_id: auth.team_id,
    bot_user_id: auth.user_id,
    bot_name: auth.user,
    connected_at: before.connected_at ?? new Date().toISOString(),
    enabled: before.enabled ?? true,
  };
  const { error } = await supabase.from("tenants").update({ settings: { ...settings, channels: { ...channels, slack } } }).eq("id", workspace.id);
  if (error) return { error: `Could not save: ${error.message}` };
  revalidatePath(`/app/${slug}`, "layout");
  return { ok: `Connected to Slack workspace ${auth.team} as @${auth.user}.` };
}

export async function disconnectSlack(formData: FormData) {
  const slug = String(formData.get("slug"));
  const { supabase, workspace } = await context(slug);
  await supabase.rpc("delete_tenant_secret", { p_tenant_id: workspace.id, p_name: SLACK_TOKEN_SECRET });
  await supabase.rpc("delete_tenant_secret", { p_tenant_id: workspace.id, p_name: SLACK_SIGNING_SECRET });
  const settings = await readSettings(supabase, workspace.id);
  const channels = { ...((settings.channels as Record<string, unknown> | undefined) ?? {}) };
  delete channels.slack;
  await supabase.from("tenants").update({ settings: { ...settings, channels } }).eq("id", workspace.id);
  revalidatePath(`/app/${slug}`, "layout");
}

export async function testSlack(_prev: FormState, formData: FormData): Promise<FormState> {
  const slug = String(formData.get("slug"));
  const { workspace } = await context(slug);
  const { data } = await createAdminClient().rpc("get_tenant_secret", { p_tenant_id: workspace.id, p_name: SLACK_TOKEN_SECRET });
  if (!data) return { error: "✗ Failed — the saved token is missing. Click Edit and paste it again." };
  const started = Date.now();
  const auth = await slackApi<AuthTest>(data as string, "auth.test", {});
  if (!auth.ok) return { error: `✗ Failed — Slack says: ${auth.error}` };
  return { ok: `✓ Connected in ${((Date.now() - started) / 1000).toFixed(1)} s — ${auth.team}, bot @${auth.user}.` };
}

// The Slack on/off switch. Keys stay saved, so switching back on is instant.
export async function setSlackEnabled(formData: FormData) {
  const slug = String(formData.get("slug"));
  const { supabase, workspace } = await context(slug);
  const enabled = formData.get("enabled") === "1";
  const settings = await readSettings(supabase, workspace.id);
  const channels = (settings.channels as Record<string, unknown> | undefined) ?? {};
  const slack = channels.slack as SlackSettings | undefined;
  if (!slack) return;
  await supabase.from("tenants").update({ settings: { ...settings, channels: { ...channels, slack: { ...slack, enabled } } } }).eq("id", workspace.id);
  revalidatePath(`/app/${slug}`, "layout");
}

// ---------------------------------------------------------------------------
// WhatsApp (Twilio). Account SID, number and files address in tenants.settings.channels.whatsapp;
// the Auth Token in Vault.
// ---------------------------------------------------------------------------
async function saveWhatsAppSettings(supabase: Awaited<ReturnType<typeof context>>["supabase"], tenantId: string, patch: Partial<WhatsAppSettings> | null) {
  const settings = await readSettings(supabase, tenantId);
  const channels = { ...((settings.channels as Record<string, unknown> | undefined) ?? {}) };
  if (patch === null) delete channels.whatsapp;
  else channels.whatsapp = { ...((channels.whatsapp as WhatsAppSettings | undefined) ?? {}), ...patch };
  return supabase.from("tenants").update({ settings: { ...settings, channels } }).eq("id", tenantId);
}

export async function connectWhatsApp(_prev: FormState, formData: FormData): Promise<FormState> {
  const slug = String(formData.get("slug"));
  const { supabase, workspace } = await context(slug);
  const sid = String(formData.get("account_sid") ?? "").trim();
  const typedToken = String(formData.get("auth_token") ?? "").trim();
  const number = String(formData.get("number") ?? "").replace(/^whatsapp:/, "").replace(/[\s()-]/g, "");
  const filesRaw = String(formData.get("files_url") ?? "").trim();
  if (!/^AC[0-9a-f]{32}$/i.test(sid)) return { error: "Paste the Account SID (starts with AC, 34 characters) from console.twilio.com." };
  if (!/^\+\d{8,15}$/.test(number)) return { error: "Enter the WhatsApp number with country code, e.g. +14155238886." };
  let files: string | null = null;
  if (filesRaw) {
    try {
      const u = new URL(filesRaw);
      if (u.protocol !== "https:") throw new Error();
      files = u.toString();
    } catch {
      return { error: "The files address must be an https:// address." };
    }
  }
  let token = typedToken;
  if (!token) {
    const { data } = await createAdminClient().rpc("get_tenant_secret", { p_tenant_id: workspace.id, p_name: TWILIO_TOKEN_SECRET });
    token = (data as string | null) ?? "";
  }
  if (token.length < 20) return { error: "Paste the Auth Token (console.twilio.com → Account Info)." };

  let account: Awaited<ReturnType<typeof twilioAccount>>;
  try {
    account = await twilioAccount(sid, token);
  } catch (e) {
    return { error: `Twilio refused the Account SID or Auth Token (${e instanceof Error ? e.message : e}).` };
  }
  if (typedToken) {
    const { error } = await supabase.rpc("set_tenant_secret", { p_tenant_id: workspace.id, p_name: TWILIO_TOKEN_SECRET, p_kind: "other", p_provider: "twilio", p_secret: token });
    if (error) return { error: `Could not save the token: ${error.message}` };
  }
  const settings = await readSettings(supabase, workspace.id);
  const before = ((settings.channels as Record<string, unknown> | undefined)?.whatsapp as WhatsAppSettings | undefined) ?? {};
  const { error } = await saveWhatsAppSettings(supabase, workspace.id, {
    account_sid: sid,
    number,
    files_url: files,
    account_name: account.friendly_name,
    enabled: before.enabled ?? true,
    connected_at: before.connected_at ?? new Date().toISOString(),
  });
  if (error) return { error: `Could not save: ${error.message}` };
  revalidatePath(`/app/${slug}`, "layout");
  return { ok: `Connected to Twilio account "${account.friendly_name}"${account.type === "Trial" ? " (trial)" : ""}.` };
}

export async function setWhatsAppEnabled(formData: FormData) {
  const slug = String(formData.get("slug"));
  const { supabase, workspace } = await context(slug);
  await saveWhatsAppSettings(supabase, workspace.id, { enabled: formData.get("enabled") === "1" });
  revalidatePath(`/app/${slug}`, "layout");
}

export async function disconnectWhatsApp(formData: FormData) {
  const slug = String(formData.get("slug"));
  const { supabase, workspace } = await context(slug);
  await supabase.rpc("delete_tenant_secret", { p_tenant_id: workspace.id, p_name: TWILIO_TOKEN_SECRET });
  await saveWhatsAppSettings(supabase, workspace.id, null);
  revalidatePath(`/app/${slug}`, "layout");
}

export async function testWhatsApp(_prev: FormState, formData: FormData): Promise<FormState> {
  const slug = String(formData.get("slug"));
  const { supabase, workspace } = await context(slug);
  const settings = await readSettings(supabase, workspace.id);
  const wa = (settings.channels as Record<string, unknown> | undefined)?.whatsapp as WhatsAppSettings | undefined;
  const { data: token } = await createAdminClient().rpc("get_tenant_secret", { p_tenant_id: workspace.id, p_name: TWILIO_TOKEN_SECRET });
  if (!wa?.account_sid || !token) return { error: "✗ Failed — the Account SID or Auth Token is missing." };
  const started = Date.now();
  try {
    const a = await twilioAccount(wa.account_sid, token as string);
    return { ok: `✓ Connected in ${((Date.now() - started) / 1000).toFixed(1)} s — ${a.friendly_name} (${a.type?.toLowerCase() ?? "account"}, ${a.status}).` };
  } catch (e) {
    return { error: `✗ Failed — ${e instanceof Error ? e.message : String(e)}` };
  }
}
