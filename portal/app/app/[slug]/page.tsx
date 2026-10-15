import { redirect } from "next/navigation";
import Link from "next/link";
import { CheckCircle2, Circle } from "lucide-react";
import { BRAND } from "@/lib/brand";
import { createClient, getUser } from "@/lib/supabase/server";
import { canManage, getWorkspace } from "@/lib/workspaces";

async function count(table: "sources" | "records" | "documents" | "tenant_members", tenantId: string) {
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
  const [sources, records, documents, members, keys] = await Promise.all([
    count("sources", workspace.id),
    count("records", workspace.id),
    count("documents", workspace.id),
    count("tenant_members", workspace.id),
    canManage(workspace.role)
      ? supabase.from("tenant_secrets").select("id", { count: "exact", head: true }).eq("tenant_id", workspace.id).eq("kind", "ai_key").then((r) => r.count ?? 0)
      : Promise.resolve(null),
  ]);

  const stats = [
    { label: "Members", value: members },
    { label: "Connected sources", value: sources },
    { label: "Synced records", value: records },
    { label: "Documents", value: documents },
  ];

  const steps = [
    { done: true, text: "Create your workspace", href: null },
    { done: members > 1, text: "Invite your colleagues", href: `/app/${slug}/members` },
    ...(keys !== null
      ? [{ done: keys > 0, text: "Add your own AI key (optional — the platform key is used otherwise)", href: `/app/${slug}/settings#ai-keys` }]
      : []),
    { done: sources > 0, text: "Connect a data source — Odoo now; SQL database and spreadsheet next", href: `/app/${slug}/settings#data-sources` },
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
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

      <p className="text-xs text-genie-muted">Plan: {workspace.plan}{workspace.document_addon ? " + Document add-on" : ""}</p>
    </div>
  );
}
