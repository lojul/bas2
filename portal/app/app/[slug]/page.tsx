import { redirect } from "next/navigation";
import Link from "next/link";
import { ArrowRight, CheckCircle2, Circle, CircleHelp, Database, MessagesSquare, Users } from "lucide-react";
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

  const shortcuts = [
    { href: `/app/${slug}/ask`, icon: MessagesSquare, title: "Ask a question", text: "Search your data in plain language" },
    ...(canManage(workspace.role)
      ? [{ href: `/app/${slug}/settings#data-sources`, icon: Database, title: "Data sources", text: "Turn Odoo on — read live, nothing stored" }]
      : []),
    { href: `/app/${slug}/members`, icon: Users, title: "Team", text: "Invite colleagues and set roles" },
    { href: `/app/${slug}/help`, icon: CircleHelp, title: "Help", text: "Step-by-step guides and beta limits" },
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4">
        {stats.map((s) => (
          <div key={s.label} className="card p-4">
            <div className="text-2xl font-semibold">{s.value.toLocaleString()}</div>
            <div className="text-sm text-genie-muted">{s.label}</div>
          </div>
        ))}
      </div>

      <div className="card">
        <h2 className="font-medium">Getting started with {BRAND.name}</h2>
        <ul className="mt-4 space-y-3">
          {steps.map((step) => (
            <li key={step.text} className="flex items-start gap-3 text-sm">
              {step.done ? (
                <CheckCircle2 size={18} className="mt-0.5 shrink-0 text-genie-green" />
              ) : (
                <Circle size={18} className="mt-0.5 shrink-0 text-genie-muted" />
              )}
              {step.href && !step.done ? (
                <Link href={step.href} className="underline underline-offset-2">{step.text}</Link>
              ) : (
                <span className={step.done ? "text-genie-muted line-through" : ""}>{step.text}</span>
              )}
            </li>
          ))}
        </ul>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {shortcuts.map((s) => (
          <Link key={s.href} href={s.href} className="card flex items-center gap-3 p-4 hover:border-genie-green">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-genie-accent text-genie-green-deep">
              <s.icon size={18} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-medium">{s.title}</span>
              <span className="block text-xs text-genie-muted">{s.text}</span>
            </span>
            <ArrowRight size={16} className="text-genie-muted" />
          </Link>
        ))}
      </div>

      <p className="text-xs text-genie-muted">Plan: {workspace.plan}{workspace.document_addon ? " + Document add-on" : ""}</p>
    </div>
  );
}
