import "server-only";
import { type LiveOdoo, liveFindContact, liveGetRecord, liveSearchRecords, liveWorkspaceInfo, openLiveOdoo } from "@/lib/odoo/live";
import { type LiveSearch, liveGetDocument, liveIndexInfo, liveSearchKnowledge } from "@/lib/search/azure";
import { createAdminClient } from "@/lib/supabase/admin";

// A workspace's switched-on data sources, read live at question time (decided 2026-10-16: Genie
// stores no copy of customer data). Odoo answers record questions (search_records, get_record,
// find_contact); a search index answers document questions (search_knowledge). Read with the
// service role because the keys come out of Vault; callers have already checked who is asking.

export type LiveSources = { odoo: LiveOdoo | null; search: LiveSearch | null };

type SourceRow = {
  name: string;
  kind: string;
  config: {
    secret_name: string;
    // Odoo
    url?: string;
    db?: string;
    login?: string | null;
    models?: string[];
    // Azure AI Search
    endpoint?: string;
    index?: string;
    semantic?: string | null;
    vector_field?: string | null;
  };
};

export async function liveSourcesFor(tenantId: string): Promise<LiveSources | null> {
  const admin = createAdminClient();
  const { data: rows } = await admin
    .from("sources")
    .select("name, kind, config")
    .eq("tenant_id", tenantId)
    .in("kind", ["odoo_json2", "odoo_xmlrpc", "azure_search"])
    .neq("status", "paused")
    .order("created_at")
    .returns<SourceRow[]>();
  if (!rows?.length) return null;

  const keyFor = async (row: SourceRow) => {
    const { data, error } = await admin.rpc("get_tenant_secret", { p_tenant_id: tenantId, p_name: row.config.secret_name });
    if (error || !data) throw new Error(`The key for "${row.name}" is missing. Open Settings → Data sources → Edit and paste the key again.`);
    return data as string;
  };

  const odooRow = rows.find((r) => r.kind.startsWith("odoo"));
  const searchRow = rows.find((r) => r.kind === "azure_search");
  const [odoo, search] = await Promise.all([
    odooRow
      ? keyFor(odooRow).then((key) => {
          const c = odooRow.config;
          return openLiveOdoo({ name: odooRow.name, kind: odooRow.kind, config: { url: c.url ?? "", db: c.db ?? "", login: c.login, models: c.models ?? [] } }, key);
        })
      : null,
    searchRow
      ? keyFor(searchRow).then((key) => {
          const c = searchRow.config;
          return { name: searchRow.name, endpoint: c.endpoint ?? "", index: c.index ?? "", semantic: c.semantic ?? null, vectorField: c.vector_field ?? null, key };
        })
      : null,
  ]);
  return { odoo, search };
}

// One tool call. Same tool names and arguments as the MCP server and Ask.
export async function runLiveTool(live: LiveSources, workspaceName: string, tool: string, args: Record<string, unknown>) {
  const limit = (n: unknown, d: number, max: number) => Math.min(Math.max(Number(n) || d, 1), max);
  const { odoo, search } = live;
  switch (tool) {
    case "workspace_info": {
      const [records, documents] = await Promise.all([
        odoo ? liveWorkspaceInfo(odoo, workspaceName) : null,
        search ? liveIndexInfo(search).catch((e) => ({ name: search.name, error: String(e instanceof Error ? e.message : e) })) : null,
      ]);
      return {
        workspace: workspaceName,
        record_sources: records?.sources ?? [],
        record_types: records?.record_types ?? [],
        document_sources: documents ? [documents] : [],
        hint: search ? "Use search_knowledge for documents (proposals, building details, reports); search_records for live business records." : undefined,
      };
    }
    case "search_records":
      if (odoo) return liveSearchRecords(odoo, args.query as string | undefined, args.object_type as string | undefined, limit(args.limit, 10, 50));
      if (search) return liveSearchKnowledge(search, String(args.query ?? ""), limit(args.limit, 10, 50));
      return { results: [] };
    case "get_record": {
      const id = String(args.id ?? "");
      if (id.startsWith("search:")) {
        if (!search) throw new Error("No search index is switched on.");
        return liveGetDocument(search, id);
      }
      if (!odoo) throw new Error("No Odoo is switched on.");
      return liveGetRecord(odoo, id);
    }
    case "find_contact":
      if (odoo) return liveFindContact(odoo, String(args.query ?? ""), limit(args.limit, 10, 50));
      return { results: [], note: "No contact source (Odoo) is switched on." };
    case "search_knowledge":
      if (search) return liveSearchKnowledge(search, String(args.query ?? ""), limit(args.limit, 8, 30));
      return { results: [], note: "No document source is switched on for this workspace." };
    default:
      throw new Error(`Unknown tool ${tool}`);
  }
}

// One tool_call usage row (the database tools over demo data meter inside the database).
export async function meterToolCall(tenantId: string, tool: string, channel: "web" | "mcp" | "slack" | "whatsapp", userId?: string | null) {
  const { error } = await createAdminClient()
    .from("usage_events")
    .insert({ tenant_id: tenantId, metric: "tool_call", quantity: 1, channel, user_id: userId ?? null, metadata: { tool, live: true } });
  if (error) console.error("tool metering failed", error.message);
}
