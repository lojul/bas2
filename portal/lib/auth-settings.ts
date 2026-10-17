import { SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from "@/lib/env";

// Google and Microsoft sign-in are set up in Supabase but not ready for users yet (decided 2026-10-17):
// the sign-in page shows them as "Coming soon". Set to true to switch them on.
export const SOCIAL_SIGNIN_READY = false;

export type AuthSettings = {
  google: boolean;
  // Supabase calls Microsoft (Entra ID) sign-in "azure".
  microsoft: boolean;
  // false when Supabase asks new users to confirm their email before they can sign in.
  autoconfirm: boolean;
};

// Which sign-in methods are switched on in Supabase (Authentication → Sign In / Providers), so the
// sign-in page shows only the buttons that work. Cached for a minute.
export async function getAuthSettings(): Promise<AuthSettings> {
  try {
    const res = await fetch(`${SUPABASE_URL}/auth/v1/settings`, {
      headers: { apikey: SUPABASE_PUBLISHABLE_KEY },
      next: { revalidate: 60 },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const s = (await res.json()) as { external?: Record<string, boolean>; mailer_autoconfirm?: boolean };
    return {
      google: Boolean(s.external?.google),
      microsoft: Boolean(s.external?.azure),
      autoconfirm: Boolean(s.mailer_autoconfirm),
    };
  } catch {
    return { google: false, microsoft: false, autoconfirm: false };
  }
}
