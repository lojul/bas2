import type { Metadata } from "next";
import { Logo } from "@/components/logo";
import { safeNextPath } from "@/lib/env";
import { ConfirmSession } from "./confirm-session";

export const metadata: Metadata = { title: "Signing in" };

// Landing page of the emailed sign-in link. The session arrives in the URL fragment, which only
// the browser can read, so a client component picks it up and stores it.
export default async function ConfirmPage({ searchParams }: PageProps<"/auth/confirm">) {
  const params = await searchParams;
  const next = safeNextPath(typeof params.next === "string" ? params.next : null);
  return (
    <main className="flex flex-1 items-center justify-center px-6 py-16">
      <div className="w-full max-w-sm">
        <Logo />
        <div className="card mt-6">
          <ConfirmSession next={next} />
        </div>
      </div>
    </main>
  );
}
