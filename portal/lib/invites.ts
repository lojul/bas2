import "server-only";
import { createHash } from "node:crypto";
import { createAdminClient } from "@/lib/supabase/admin";

// An invitation looked up by the raw token from its link (service role: the visitor may not have an
// account yet). Only the token's SHA-256 is stored.
export type InvitationInfo = { email: string; role: string; workspace: string; slug: string; expired: boolean; used: boolean };

export async function findInvitation(token: string): Promise<InvitationInfo | null> {
  if (!/^[A-Za-z0-9_-]{20,100}$/.test(token)) return null;
  const tokenHash = createHash("sha256").update(token).digest("hex");
  const { data } = await createAdminClient()
    .from("invitations")
    .select("email, role, expires_at, accepted_at, tenants!inner(name, slug)")
    .eq("token_hash", tokenHash)
    .maybeSingle<{ email: string; role: string; expires_at: string; accepted_at: string | null; tenants: { name: string; slug: string } }>();
  if (!data) return null;
  return {
    email: data.email,
    role: data.role,
    workspace: data.tenants.name,
    slug: data.tenants.slug,
    expired: new Date(data.expires_at) < new Date(),
    used: data.accepted_at !== null,
  };
}
