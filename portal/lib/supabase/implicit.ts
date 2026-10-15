import { createClient } from "@supabase/supabase-js";
import { SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from "@/lib/env";

// Starts email sign-in with Supabase's implicit flow: the emailed link returns the session in the
// URL fragment, read by /auth/confirm. Unlike the PKCE flow it does not depend on a code-verifier
// cookie surviving between requesting the link and opening it (on genie.infiniduo.com that cookie
// never came back: AuthPKCECodeVerifierMissingError), and it works when the email is opened on
// another device. Stateless: it never stores a session itself.
export function createImplicitClient() {
  return createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
    auth: { flowType: "implicit", persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
  });
}
