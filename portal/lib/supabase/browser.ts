import { createBrowserClient } from "@supabase/ssr";
import { SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from "@/lib/env";

// Supabase client for client components. It stores the session in the same cookies the server
// client and proxy.ts read.
//
// Implicit flow: Google sign-in and email confirmation links return the session in the URL
// fragment, which /auth/confirm stores. The PKCE flow needs a code-verifier cookie to survive the
// round trip, and on genie.infiniduo.com it never came back (AuthPKCECodeVerifierMissingError).
export function createClient() {
  return createBrowserClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
    auth: { flowType: "implicit" },
  });
}
