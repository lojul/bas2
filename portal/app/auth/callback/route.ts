import { NextResponse, type NextRequest } from "next/server";
import type { EmailOtpType } from "@supabase/supabase-js";
import { safeNextPath } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";

// Landing point of the emailed sign-in link. Handles both the PKCE `code` form (default email
// template) and the `token_hash` form (custom template), then sends the user on to `next`.
export async function GET(request: NextRequest) {
  const url = request.nextUrl;
  const next = safeNextPath(url.searchParams.get("next"));
  const code = url.searchParams.get("code");
  const tokenHash = url.searchParams.get("token_hash");
  const type = url.searchParams.get("type") as EmailOtpType | null;

  const supabase = await createClient();
  let error: { name?: string; message: string } | null = { message: "no code or token_hash in the link" };
  if (code) {
    ({ error } = await supabase.auth.exchangeCodeForSession(code));
  } else if (tokenHash && type) {
    ({ error } = await supabase.auth.verifyOtp({ type, token_hash: tokenHash }));
  }
  const ok = !error;
  // Shows up in Vercel's runtime logs, so a failed sign-in can be diagnosed.
  if (error) console.error("auth/callback failed:", error.name ?? "Error", error.message);

  if (ok) return NextResponse.redirect(new URL(next, request.url));
  const login = new URL("/login", request.url);
  login.searchParams.set("error", "link");
  login.searchParams.set("next", next);
  return NextResponse.redirect(login);
}
