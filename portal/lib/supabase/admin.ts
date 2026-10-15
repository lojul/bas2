import { createClient } from "@supabase/supabase-js";
import { SUPABASE_URL } from "@/lib/env";

// Service-role client for server code only (never import from a client component).
// Used for what signed-in users must not do themselves: reading decrypted workspace keys from
// Vault (get_tenant_secret) and recording token usage. Needs SUPABASE_SECRET_KEY (Vercel env).
export function createAdminClient() {
  const key = process.env.SUPABASE_SECRET_KEY;
  if (!key) throw new Error("SUPABASE_SECRET_KEY is not set (Supabase → Project Settings → API Keys → secret key)");
  return createClient(SUPABASE_URL, key, { auth: { persistSession: false, autoRefreshToken: false } });
}

export const hasAdminClient = () => Boolean(process.env.SUPABASE_SECRET_KEY);
