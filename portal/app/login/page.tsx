import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Logo } from "@/components/logo";
import { BRAND } from "@/lib/brand";
import { safeNextPath } from "@/lib/env";
import { SOCIAL_SIGNIN_READY, getAuthSettings } from "@/lib/auth-settings";
import { getUser } from "@/lib/supabase/server";
import { AuthPanel } from "./auth-panel";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const params = await searchParams;
  const next = safeNextPath(typeof params.next === "string" ? params.next : null);
  const failed = params.error === "link";
  // Short technical code from /auth/confirm (e.g. otp_expired), shown to help support.
  const reason = typeof params.reason === "string" ? params.reason.replace(/[^\w.-]/g, "").slice(0, 60) : null;

  const { user } = await getUser();
  if (user) redirect(next);
  const settings = await getAuthSettings();
  const google = SOCIAL_SIGNIN_READY && settings.google;
  const microsoft = SOCIAL_SIGNIN_READY && settings.microsoft;
  const social = [google && "Google", microsoft && "Microsoft"].filter(Boolean).join(" or ");

  return (
    <main className="flex flex-1 items-center justify-center px-6 py-16">
      <div className="w-full max-w-sm">
        <Logo />
        <div className="card mt-6">
          <h1 className="text-xl font-semibold">Sign in to {BRAND.name}</h1>
          <p className="mb-5 mt-1 text-sm text-genie-muted">
            New here? Choose &ldquo;Create account&rdquo;{social ? ` or continue with ${social}` : ""}.
          </p>
          {failed && (
            <p className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-genie-danger">
              Sign-in didn&apos;t complete. Please try again.
              {reason && <span className="mt-1 block font-mono text-xs opacity-70">Reason: {reason}</span>}
            </p>
          )}
          <AuthPanel next={next} google={google} microsoft={microsoft} comingSoon={!SOCIAL_SIGNIN_READY} autoconfirm={settings.autoconfirm} />
          <p className="mt-5 text-xs text-genie-muted">
            By continuing you agree to the <Link href="/terms" className="underline underline-offset-2">Terms of Service</Link>{" "}
            and acknowledge the <Link href="/privacy" className="underline underline-offset-2">Privacy Policy</Link>.
          </p>
        </div>
      </div>
    </main>
  );
}
