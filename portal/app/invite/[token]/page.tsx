import type { Metadata } from "next";
import Link from "next/link";
import { Logo } from "@/components/logo";
import { BRAND } from "@/lib/brand";
import { findInvitation } from "@/lib/invites";
import { ROLE_LABEL, type Role } from "@/lib/roles";
import { getUser } from "@/lib/supabase/server";
import { AcceptForm, CreatePasswordForm } from "./accept-form";

export const metadata: Metadata = { title: "Invitation" };

export default async function InvitePage({ params }: PageProps<"/invite/[token]">) {
  const { token } = await params;
  const [{ user }, invite] = await Promise.all([getUser(), findInvitation(token)]);
  const signIn = `/login?next=${encodeURIComponent(`/invite/${token}`)}`;

  let body: React.ReactNode;
  if (!invite || invite.expired || invite.used) {
    body = (
      <>
        <h1 className="text-xl font-semibold">This invitation can&apos;t be used</h1>
        <p className="mt-1 text-sm text-genie-muted">It has expired, was already used, or the link is incomplete. Ask the person who invited you for a new link.</p>
      </>
    );
  } else if (user) {
    const sameEmail = user.email?.toLowerCase() === invite.email;
    body = (
      <>
        <h1 className="text-xl font-semibold">Join {invite.workspace}</h1>
        <p className="mb-5 mt-1 text-sm text-genie-muted">
          as {ROLE_LABEL[invite.role as Role] ?? invite.role}, signed in as <strong className="text-genie-ink">{user.email}</strong>.
        </p>
        {sameEmail ? (
          <AcceptForm token={token} />
        ) : (
          <p className="text-sm text-genie-danger">
            This invitation is for {invite.email}. Sign out and sign in with that address.
          </p>
        )}
      </>
    );
  } else {
    body = (
      <>
        <h1 className="text-xl font-semibold">Join {invite.workspace}</h1>
        <p className="mb-5 mt-1 text-sm text-genie-muted">
          You&apos;re invited to {BRAND.name}{" "}as {ROLE_LABEL[invite.role as Role] ?? invite.role}. Create your password to join.
        </p>
        <CreatePasswordForm token={token} email={invite.email} />
        <div className="mt-5 space-y-1 border-t border-genie-border pt-4 text-sm text-genie-muted">
          <p>
            Already have an account?{" "}
            <Link href={signIn} className="text-genie-ink underline underline-offset-2">Sign in</Link>
          </p>
          <p>
            Or <Link href={signIn} className="text-genie-ink underline underline-offset-2">continue with Microsoft or Google</Link> using{" "}
            {invite.email}.
          </p>
        </div>
      </>
    );
  }

  return (
    <main className="flex flex-1 items-center justify-center px-6 py-16">
      <div className="w-full max-w-sm">
        <Logo />
        <div className="card mt-6">{body}</div>
      </div>
    </main>
  );
}
