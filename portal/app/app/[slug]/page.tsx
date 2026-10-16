import { redirect } from "next/navigation";
import Link from "next/link";
import { ArrowUpRight, CheckCircle2, Circle } from "lucide-react";
import { BRAND } from "@/lib/brand";
import { createClient, getUser } from "@/lib/supabase/server";
import { canManage, getWorkspace } from "@/lib/workspaces";

async function count(table: "sources" | "tenant_members", tenantId: string) {
  const supabase = await createClient();
  const { count } = await supabase.from(table).select("*", { count: "exact", head: true }).eq("tenant_id", tenantId);
  return count ?? 0;
}

export default async function OverviewPage({ params }: PageProps<"/app/[slug]">) {
  const { slug } = await params;
  const { user } = await getUser();
  if (!user) redirect("/login");
  const workspace = (await getWorkspace(user.id, slug))!;

  const supabase = await createClient();
  const [sources, members, keys] = await Promise.all([
    count("sources", workspace.id),
    count("tenant_members", workspace.id),
    canManage(workspace.role)
      ? supabase.from("tenant_secrets").select("id", { count: "exact", head: true }).eq("tenant_id", workspace.id).eq("kind", "ai_key").then((r) => r.count ?? 0)
      : Promise.resolve(null),
  ]);

  const stats = [
    { label: "Members", value: members },
    { label: "Data sources (read live)", value: sources },
  ];

  const steps = [
    { done: true, text: "Create your workspace", href: null },
    { done: members > 1, text: "Invite your colleagues", href: `/app/${slug}/members` },
    ...(keys !== null
      ? [{ done: keys > 0, text: "Add your own AI key (optional — the platform key is used otherwise)", href: `/app/${slug}/settings#ai-keys` }]
      : []),
    { done: sources > 0, text: "Turn on a data source — Odoo now; SQL databases next", href: `/app/${slug}/settings#data-sources` },
  ];

  const base = `/app/${slug}`;
  const manage = canManage(workspace.role);
  const shortcuts = [
    { href: `${base}/ask`, label: "Ask a question" },
    ...(manage ? [{ href: `${base}/settings#data-sources`, label: "Data sources" }] : []),
    { href: `${base}/members`, label: "Team" },
    { href: `${base}/help`, label: "Help" },
  ];
  // Link lists, like ERPNext's "Reports & Masters" cards.
  const groups = [
    { title: "Ask", links: [{ href: `${base}/ask`, label: "Ask a question" }, { href: `${base}/help`, label: "How to ask good questions" }] },
    ...(manage
      ? [
          {
            title: "Settings",
            links: [
              { href: `${base}/settings#data-sources`, label: "Data sources" },
              { href: `${base}/settings#ai-keys`, label: "AI model keys" },
              { href: `${base}/settings#ai-agents`, label: "AI agent access (MCP)" },
            ],
          },
        ]
      : []),
    { title: "Team", links: [{ href: `${base}/members`, label: "Members and invitations" }] },
    { title: "Help", links: [{ href: `${base}/help`, label: "Getting started" }, { href: `${base}/help`, label: "Beta limits" }] },
  ];

  return (
    <div className="space-y-8">
      <div className="grid gap-4 sm:grid-cols-3">
        {[...stats, { label: "Plan", value: `${workspace.plan}${workspace.document_addon ? " + documents" : ""}` }].map((s) => (
          <div key={s.label} className="card p-4">
            <div className="text-xs text-genie-muted">{s.label}</div>
            <div className="mt-1 text-2xl font-semibold capitalize">{typeof s.value === "number" ? s.value.toLocaleString() : s.value}</div>
          </div>
        ))}
      </div>

      <section>
        <h2 className="mb-3 text-base font-semibold">Your shortcuts</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {shortcuts.map((s) => (
            <Link key={s.href} href={s.href} className="card flex items-center justify-between px-4 py-3 text-sm font-medium hover:bg-genie-accent">
              {s.label}
              <ArrowUpRight size={14} className="text-genie-muted" />
            </Link>
          ))}
        </div>
      </section>

      <section className="card">
        <h2 className="text-base font-semibold">Getting started with {BRAND.name}</h2>
        <ul className="mt-3 divide-y divide-genie-border">
          {steps.map((step) => (
            <li key={step.text} className="flex items-start gap-3 py-2.5 text-sm">
              {step.done ? (
                <CheckCircle2 size={17} className="mt-0.5 shrink-0 text-genie-green" />
              ) : (
                <Circle size={17} className="mt-0.5 shrink-0 text-genie-muted" />
              )}
              {step.href && !step.done ? (
                <Link href={step.href} className="hover:underline">{step.text}</Link>
              ) : (
                <span className={step.done ? "text-genie-muted line-through" : ""}>{step.text}</span>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="mb-3 text-base font-semibold">Pages</h2>
        <div className="grid gap-x-8 gap-y-6 sm:grid-cols-2 lg:grid-cols-4">
          {groups.map((g) => (
            <div key={g.title}>
              <h3 className="mb-2 text-sm font-semibold">{g.title}</h3>
              <ul className="space-y-1.5">
                {g.links.map((l) => (
                  <li key={l.label}>
                    <Link href={l.href} className="inline-flex items-center gap-1 text-sm text-genie-ink/80 hover:text-genie-ink hover:underline">
                      {l.label} <ArrowUpRight size={12} className="text-genie-muted" />
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
