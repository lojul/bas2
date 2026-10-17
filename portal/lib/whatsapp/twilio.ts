import "server-only";
import { createHmac, timingSafeEqual } from "node:crypto";
import { createAdminClient } from "@/lib/supabase/admin";
import { TWILIO_TOKEN_SECRET } from "./names";

export { TWILIO_TOKEN_SECRET };

// Genie on WhatsApp through Twilio (the Sandbox for now). Twilio posts each incoming message to
// /api/whatsapp/<workspace slug>/inbound. Text questions are answered by Genie; messages with a photo
// or file are passed on unchanged to files_url (C21: its n8n document intake). Nothing is stored.

export type WhatsAppSettings = {
  enabled?: boolean;
  account_sid?: string;
  number?: string; // the WhatsApp sender, e.g. +14155238886 (Twilio Sandbox)
  files_url?: string | null;
  account_name?: string;
  connected_at?: string;
};

// Twilio signs requests: base64(HMAC-SHA1(auth token, full URL + each POST param name+value, sorted by name)).
export function verifyTwilioSignature(authToken: string, url: string, params: URLSearchParams, signature: string | null) {
  if (!signature) return false;
  const data = [...new Set(params.keys())]
    .sort()
    .reduce((acc, key) => acc + params.getAll(key).map((v) => key + v).join(""), url);
  const expected = createHmac("sha1", authToken).update(data).digest("base64");
  const a = Buffer.from(expected);
  const b = Buffer.from(signature);
  return a.length === b.length && timingSafeEqual(a, b);
}

const auth = (sid: string, token: string) => `Basic ${Buffer.from(`${sid}:${token}`).toString("base64")}`;

export async function twilioAccount(sid: string, token: string) {
  const res = await fetch(`https://api.twilio.com/2010-04-01/Accounts/${encodeURIComponent(sid)}.json`, {
    headers: { Authorization: auth(sid, token) },
    cache: "no-store",
  });
  const body = (await res.json().catch(() => ({}))) as { friendly_name?: string; status?: string; type?: string; message?: string };
  if (!res.ok) throw new Error(body.message ?? `Twilio returned HTTP ${res.status}`);
  return body;
}

// WhatsApp messages are limited to 1,600 characters; longer answers go out in parts.
export async function sendWhatsApp(sid: string, token: string, from: string, to: string, text: string) {
  const parts: string[] = [];
  for (let rest = text; rest.length > 0; ) {
    const cut = rest.length <= 1500 ? rest.length : Math.max(rest.lastIndexOf("\n", 1500), 1000);
    parts.push(rest.slice(0, cut));
    rest = rest.slice(cut).trimStart();
  }
  for (const part of parts.slice(0, 4)) {
    const res = await fetch(`https://api.twilio.com/2010-04-01/Accounts/${encodeURIComponent(sid)}/Messages.json`, {
      method: "POST",
      headers: { Authorization: auth(sid, token), "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ From: `whatsapp:${from}`, To: to, Body: part }),
    });
    if (!res.ok) console.error("whatsapp send failed", res.status, (await res.text()).slice(0, 300));
  }
}

// Markdown (as the model writes it) → WhatsApp formatting.
export function toWhatsAppText(md: string): string {
  return md
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, "$1: $2")
    .replace(/^#{1,6}\s+(.+)$/gm, "*$1*")
    .replace(/\*\*([^*]+)\*\*/g, "*$1*")
    .replace(/^(\s*)[-*]\s+/gm, "$1• ");
}

export async function whatsappWorkspace(slug: string) {
  const admin = createAdminClient();
  const { data: tenant } = await admin
    .from("tenants")
    .select("id, name, status, settings")
    .eq("slug", slug)
    .maybeSingle<{ id: string; name: string; status: string; settings: { channels?: { whatsapp?: WhatsAppSettings } } | null }>();
  const wa = tenant?.settings?.channels?.whatsapp;
  if (!tenant || tenant.status !== "active" || !wa?.account_sid || !wa.number) return null;
  const { data: token } = await admin.rpc("get_tenant_secret", { p_tenant_id: tenant.id, p_name: TWILIO_TOKEN_SECRET });
  if (!token) return null;
  return { id: tenant.id, name: tenant.name, wa, token: token as string };
}
