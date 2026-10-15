import { redirect } from "next/navigation";
import { Bot } from "lucide-react";
import { BRAND } from "@/lib/brand";
import { SITE_URL } from "@/lib/env";
import { createClient, getUser } from "@/lib/supabase/server";
import { canManage, getWorkspace } from "@/lib/workspaces";
import { revokeApiKey } from "./actions";
import { KeyForm } from "./key-form";


type ApiKeyRow = {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
};

const TOOLS = [
  ["workspace_info", "what data this workspace holds"],
  ["search_records", "keyword search over customers, products, orders and other records"],
  ["get_record", "every field of one record"],
  ["find_contact", "people and companies by name, email or phone"],
  ["search_knowledge", "passages from policies and documents"],
];

export async function AgentsSection({ slug }: { slug: string }) {
  const { user } = await getUser();
  if (!user) redirect("/login");
  const workspace = (await getWorkspace(user.id, slug))!;
  if (!canManage(workspace.role)) {
    return <p className="text-sm text-genie-muted">Only owners and admins can manage API keys.</p>;
  }

  const supabase = await createClient();
  const { data } = await supabase
    .from("api_keys")
    .select("id, name, prefix, created_at, last_used_at, revoked_at")
    .eq("tenant_id", workspace.id)
    .order("created_at", { ascending: false });
  const keys = (data ?? []) as ApiKeyRow[];
  const endpoint = `${SITE_URL}/api/mcp`;

  return (
    <div className="space-y-6">
      <section className="card">
        <div className="flex items-center gap-2">
          <Bot size={18} className="text-genie-green" />
          <h2 className="font-medium">Connect an AI agent (MCP)</h2>
        </div>
        <p className="mb-4 mt-1 text-sm text-genie-muted">
          Let Claude, ChatGPT or your own agent use {BRAND.name}&apos;s tools on {workspace.name}&apos;s data through the
          Model Context Protocol. Each key gives read-only access to this workspace only. Tool calls count towards your plan.
        </p>
        <KeyForm slug={slug} endpoint={endpoint} />
        <div className="mt-5 text-sm">
          <div className="font-medium">Tools available</div>
          <ul className="mt-1 space-y-0.5 text-genie-muted">
            {TOOLS.map(([name, text]) => (
              <li key={name}><code className="font-mono text-xs text-genie-ink">{name}</code> — {text}</li>
            ))}
          </ul>
        </div>
      </section>

      <section>
        <h2 className="mb-2 font-medium">API keys</h2>
        {keys.length === 0 ? (
          <p className="text-sm text-genie-muted">No keys yet.</p>
        ) : (
          <ul className="divide-y divide-genie-border rounded-xl border border-genie-border bg-genie-card">
            {keys.map((k) => (
              <li key={k.id} className="flex items-center justify-between gap-3 px-5 py-3 text-sm">
                <div>
                  <div className="font-medium">
                    {k.name} {k.revoked_at && <span className="ml-1 text-xs text-genie-danger">revoked</span>}
                  </div>
                  <div className="font-mono text-xs text-genie-muted">
                    {k.prefix}… · created {new Date(k.created_at).toLocaleDateString()} ·{" "}
                    {k.last_used_at ? `last used ${new Date(k.last_used_at).toLocaleString()}` : "never used"}
                  </div>
                </div>
                {!k.revoked_at && (
                  <form action={revokeApiKey}>
                    <input type="hidden" name="slug" value={slug} />
                    <input type="hidden" name="id" value={k.id} />
                    <button type="submit" className="btn-danger">Revoke</button>
                  </form>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
