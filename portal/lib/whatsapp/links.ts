import "server-only";
import { createHash, randomInt } from "node:crypto";
import { createAdminClient } from "@/lib/supabase/admin";
import { BRAND } from "@/lib/brand";
import type { Role } from "@/lib/roles";

// Which member a WhatsApp number belongs to (table whatsapp_links). A member clicks "Link WhatsApp"
// on the Members page, gets a 6-digit code and sends "LINK <code>" from the phone; the inbound
// webhook then stores the number. Genie answers on WhatsApp only for linked numbers.

const CODE_MINUTES = 10;
const hash = (code: string) => createHash("sha256").update(code).digest("hex");

export const LINK_MESSAGE = /^link\s*(\d{6})$/i;

export async function startLink(tenantId: string, userId: string) {
  const code = String(randomInt(0, 1_000_000)).padStart(6, "0");
  const expiresAt = new Date(Date.now() + CODE_MINUTES * 60_000).toISOString();
  const { error } = await createAdminClient()
    .from("whatsapp_links")
    .upsert({ tenant_id: tenantId, user_id: userId, code_hash: hash(code), code_expires_at: expiresAt }, { onConflict: "tenant_id,user_id" });
  if (error) throw new Error(error.message);
  return { code, expiresAt };
}

// Called with the sender's number (E.164, "+852…") and the code from its message.
export async function completeLink(tenantId: string, phone: string, code: string): Promise<string> {
  const admin = createAdminClient();
  const { data: row } = await admin
    .from("whatsapp_links")
    .select("user_id")
    .eq("tenant_id", tenantId)
    .eq("code_hash", hash(code))
    .gt("code_expires_at", new Date().toISOString())
    .maybeSingle<{ user_id: string }>();
  if (!row) return `That code is wrong or has expired. On ${BRAND.name}, open Members → Your WhatsApp → Link WhatsApp for a new one.`;

  const { data: other } = await admin
    .from("whatsapp_links")
    .select("user_id")
    .eq("tenant_id", tenantId)
    .eq("phone", phone)
    .neq("user_id", row.user_id)
    .maybeSingle();
  if (other) return "This number is already linked to another member of this workspace. Ask them to unlink it first.";

  const { error } = await admin
    .from("whatsapp_links")
    .update({ phone, linked_at: new Date().toISOString(), code_hash: null, code_expires_at: null })
    .eq("tenant_id", tenantId)
    .eq("user_id", row.user_id);
  if (error) return `Could not link this number: ${error.message}`;
  return `✓ Linked. You can now ask ${BRAND.name} here.`;
}

export async function unlink(tenantId: string, userId: string) {
  const { error } = await createAdminClient().from("whatsapp_links").delete().eq("tenant_id", tenantId).eq("user_id", userId);
  if (error) throw new Error(error.message);
}

export async function memberByPhone(tenantId: string, phone: string): Promise<{ userId: string; role: Role } | null> {
  const admin = createAdminClient();
  const { data: link } = await admin.from("whatsapp_links").select("user_id").eq("tenant_id", tenantId).eq("phone", phone).maybeSingle<{ user_id: string }>();
  if (!link) return null;
  const { data: member } = await admin
    .from("tenant_members")
    .select("role")
    .eq("tenant_id", tenantId)
    .eq("user_id", link.user_id)
    .maybeSingle<{ role: Role }>();
  return member ? { userId: link.user_id, role: member.role } : null;
}

// "+85291234567" → "+852 •••• 4567" for lists.
export const maskPhone = (phone: string) => `${phone.slice(0, phone.length > 11 ? 4 : 3)} •••• ${phone.slice(-4)}`;
