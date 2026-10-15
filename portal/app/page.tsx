import Link from "next/link";
import { redirect } from "next/navigation";
import { Database, MessagesSquare, ShieldCheck } from "lucide-react";
import { Logo } from "@/components/logo";
import { BRAND } from "@/lib/brand";
import { getUser } from "@/lib/supabase/server";

export default async function Home() {
  const { user } = await getUser();
  if (user) redirect("/app");

  const points = [
    { icon: Database, title: "Your data, connected", text: "SQL databases, spreadsheets and Odoo, read into one searchable store." },
    { icon: MessagesSquare, title: "Ask where you work", text: "Web, Slack, WhatsApp and Teams — one assistant, same answers." },
    { icon: ShieldCheck, title: "Yours alone", text: "Every company's data is kept separate, and your keys stay encrypted." },
  ];

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col px-6 py-10">
      <header className="flex items-center justify-between">
        <Logo />
        <Link href="/login" className="btn-secondary">Sign in</Link>
      </header>

      <section className="mt-20 max-w-2xl">
        <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">{BRAND.tagline}</h1>
        <p className="mt-4 text-lg text-genie-muted">
          {BRAND.name}{" "}reads your company&apos;s systems and answers your team&apos;s questions — your systems stay
          the source of truth.
        </p>
        <Link href="/login" className="btn mt-8">Get started</Link>
      </section>

      <section className="mt-16 grid gap-4 sm:grid-cols-3">
        {points.map(({ icon: Icon, title, text }) => (
          <div key={title} className="card">
            <Icon size={20} className="text-genie-green" />
            <h2 className="mt-3 font-medium">{title}</h2>
            <p className="mt-1 text-sm text-genie-muted">{text}</p>
          </div>
        ))}
      </section>

      <footer className="mt-auto pt-16 text-xs text-genie-muted">© {BRAND.company}</footer>
    </main>
  );
}
