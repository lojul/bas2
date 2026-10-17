import { createServerClient } from "@supabase/ssr";
import { cache } from "react";
import { cookies } from "next/headers";
import { SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from "@/lib/env";

// Supabase client for Server Components, Server Actions and Route Handlers.
// It acts as the signed-in user, so row-level security applies to every query.
export async function createClient() {
  const cookieStore = await cookies();
  return createServerClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) => cookieStore.set(name, value, options));
        } catch {
          // Called from a Server Component, where cookies are read-only. proxy.ts refreshes the session.
        }
      },
    },
  });
}

// Once per request: layouts, the page and each Settings tab all ask for the user, and every
// auth.getUser() is a round trip to Supabase. React's cache() shares one answer within a request.
export const getUser = cache(async () => {
  const supabase = await createClient();
  const { data } = await supabase.auth.getUser();
  return { supabase, user: data.user };
});
