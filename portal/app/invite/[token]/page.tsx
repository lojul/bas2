import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Logo } from "@/components/logo";
import { BRAND } from "@/lib/brand";
import { getUser } from "@/lib/supabase/server";
import { AcceptForm } from "./accept-form";

export const metadata: Metadata = { title: "Invitation" };

export default async function InvitePage({ params }: PageProps<"/invite/[token]">) {
  const { token } = await params;
  const { user } = await getUser();
  if (!user) redirect(`/login?next=${encodeURIComponent(`/invite/${token}`)}`);

  return (
    <main className="flex flex-1 items-center justify-center px-6 py-16">
      <div className="w-full max-w-sm">
        <Logo />
        <div className="card mt-6">
          <h1 className="text-xl font-semibold">You&apos;ve been invited</h1>
          <p className="mb-5 mt-1 text-sm text-genie-muted">
            Join a workspace on {BRAND.name}{" "}as <strong className="text-genie-ink">{user.email}</strong>. The invitation
            must have been sent to this address.
          </p>
          <AcceptForm token={token} />
        </div>
      </div>
    </main>
  );
}
