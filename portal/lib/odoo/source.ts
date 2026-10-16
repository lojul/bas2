import "server-only";
import { createAdminClient } from "@/lib/supabase/admin";
import { type LiveOdoo, liveFindContact, liveGetRecord, liveSearchRecords, liveWorkspaceInfo, openLiveOdoo } from "./live";

// The workspace's live Odoo, if one is switched on. Read with the service role because the
// Odoo API key comes out of Vault; callers have already checked who is asking (membership or
// MCP API key).
export async function liveOdooFor(tenantId: string): Promise<LiveOdoo | null> {
  const admin = createAdminClient();
  const { data: source } = await admin
    .from("sources")
    .select("name, kind, status, config")
    .eq("tenant_id", tenantId)
    .like("kind", "odoo%")
    .neq("status", "paused")
    .order("created_at")
    .limit(1)
    .maybeSingle<{ name: string; kind: string; status: string; config: { url: string; db: string; login?: string | null; models: string[]; secret_name: string } }>();
  if (!source) return null;
  const { data: apiKey, error } = await admin.rpc("get_tenant_secret", { p_tenant_id: tenantId, p_name: source.config.secret_name });
  if (error || !apiKey) throw new Error("The Odoo API key is missing. Turn Odoo off and on again in Settings → Data sources.");
  return openLiveOdoo(source, apiKey as string);
}

// One tool call against live Odoo. Same tool names and arguments as the MCP server and Ask.
export async function runLiveTool(live: LiveOdoo, workspaceName: string, tool: string, args: Record<string, unknown>) {
  const limit = (n: unknown, d: number, max: number) => Math.min(Math.max(Number(n) || d, 1), max);
  switch (tool) {
    case "workspace_info":
      return liveWorkspaceInfo(live, workspaceName);
    case "search_records":
      return liveSearchRecords(live, args.query as string | undefined, args.object_type as string | undefined, limit(args.limit, 10, 50));
    case "get_record":
      return liveGetRecord(live, String(args.id ?? ""));
    case "find_contact":
      return liveFindContact(live, String(args.query ?? ""), limit(args.limit, 10, 50));
    case "search_knowledge":
      return { results: [], note: "No documents or policies are connected to this workspace yet." };
    default:
      throw new Error(`Unknown tool ${tool}`);
  }
}

// One tool_call usage row (the old database tools metered inside the database).
export async function meterToolCall(tenantId: string, tool: string, channel: "web" | "mcp", userId?: string | null) {
  const { error } = await createAdminClient()
    .from("usage_events")
    .insert({ tenant_id: tenantId, metric: "tool_call", quantity: 1, channel, user_id: userId ?? null, metadata: { tool, live: true } });
  if (error) console.error("tool metering failed", error.message);
}
