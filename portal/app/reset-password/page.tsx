import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Logo } from "@/components/logo";
import { getUser } from "@/lib/supabase/server";
import { NewPasswordForm } from "./new-password-form";

export const metadata: Metadata = { title: "Choose a new password" };

// Opened from the password-reset email: /auth/confirm has already signed the user in. Signed-in
// users can also come here to change their password.
export default async function ResetPasswordPage() {
  const { user } = await getUser();
  if (!user) redirect("/login?next=/reset-password");

  return (
    <main className="flex flex-1 items-center justify-center px-6 py-16">
      <div className="w-full max-w-sm">
        <Logo />
        <div className="card mt-6">
          <h1 className="text-xl font-semibold">Choose a new password</h1>
          <p className="mb-5 mt-1 text-sm text-genie-muted">For {user.email}.</p>
          <NewPasswordForm />
          <Link href="/app" className="mt-4 inline-block text-xs text-genie-muted underline underline-offset-2">Cancel</Link>
        </div>
      </div>
    </main>
  );
}
