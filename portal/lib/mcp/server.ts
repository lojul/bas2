import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { createClient } from "@supabase/supabase-js";
import { z } from "zod";
import { BRAND } from "@/lib/brand";
import { SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from "@/lib/env";

// The Genie MCP server: read tools over one workspace's synced data.
//
// Every tool is a single call to a SECURITY DEFINER database function (shared/ migration
// 20261015000700_mcp.sql) that resolves the API key to its workspace, meters the call and only
// reads that workspace's rows. This server holds no database secret; it uses the public key.

type RpcError = { code?: string; message: string };

function db() {
  return createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

function asText(value: unknown) {
  return { content: [{ type: "text" as const, text: JSON.stringify(value, null, 2) }] };
}

function asError(error: RpcError) {
  const text =
    error.code === "28000"
      ? `Invalid or revoked ${BRAND.name} API key. Create a new key in the ${BRAND.name} portal (workspace → AI agents).`
      : error.code === "22023"
        ? `Invalid input: ${error.message}`
        : `${BRAND.name} could not complete this request: ${error.message}`;
  return { isError: true, content: [{ type: "text" as const, text }] };
}

async function call(fn: string, args: Record<string, unknown>) {
  const { data, error } = await db().rpc(fn, args);
  if (error) return asError(error);
  return asText(data ?? null);
}

const readOnly = { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false };

export function createGenieMcpServer(apiKey: string) {
  const server = new McpServer(
    { name: `${BRAND.name.toLowerCase()}-mcp`, version: "0.1.0" },
    {
      instructions:
        `${BRAND.name} gives read access to one company's own business data (customers, contacts, products, ` +
        `orders, listings, policies and documents), synced from its systems such as SQL databases, spreadsheets ` +
        `or Odoo. Start with workspace_info to see what record types exist, then use search_records, ` +
        `find_contact or search_knowledge, and get_record for full details. Quote the record title or id ` +
        `when you use a fact, and say when nothing relevant was found instead of guessing.`,
    },
  );

  server.registerTool(
    "workspace_info",
    {
      title: "Workspace overview",
      description: "Name of the workspace, its connected data sources and the record types it holds (with counts). Call this first.",
      inputSchema: {},
      annotations: readOnly,
    },
    () => call("mcp_workspace", { p_key: apiKey }),
  );

  server.registerTool(
    "search_records",
    {
      title: "Search records",
      description:
        "Keyword search over the company's synced records (e.g. contacts, products, sales orders, listings, policies). " +
        "Matches titles, text and field values; works for Chinese too. Optionally limit to one object_type from workspace_info. " +
        "Returns id, type, title and a snippet; use get_record for all fields.",
      inputSchema: {
        query: z.string().max(200).optional().describe("Words to look for. Omit to list the most recent records."),
        object_type: z.string().max(100).optional().describe("Only this record type, e.g. 'product' or 'sales_order'."),
        limit: z.number().int().min(1).max(50).optional().describe("Maximum results (default 10)."),
      },
      annotations: readOnly,
    },
    ({ query, object_type, limit }) =>
      call("mcp_search_records", { p_key: apiKey, p_query: query ?? null, p_object_type: object_type ?? null, p_limit: limit ?? 10 }),
  );

  server.registerTool(
    "get_record",
    {
      title: "Get record",
      description: "All fields of one record, by the id returned from search_records or find_contact.",
      inputSchema: { id: z.uuid().describe("Record id.") },
      annotations: readOnly,
    },
    ({ id }) => call("mcp_get_record", { p_key: apiKey, p_id: id }),
  );

  server.registerTool(
    "find_contact",
    {
      title: "Find contact",
      description: "Find people and companies by name, company, email or phone number (any format; matched on digits).",
      inputSchema: {
        query: z.string().min(2).max(200).describe("Name, company, email or phone number."),
        limit: z.number().int().min(1).max(50).optional().describe("Maximum results (default 10)."),
      },
      annotations: readOnly,
    },
    ({ query, limit }) => call("mcp_find_contact", { p_key: apiKey, p_query: query, p_limit: limit ?? 10 }),
  );

  server.registerTool(
    "search_knowledge",
    {
      title: "Search knowledge",
      description:
        "Search passages of longer text such as policies, procedures and uploaded documents. " +
        "Use for 'how do we…' or 'what is our policy on…' questions.",
      inputSchema: {
        query: z.string().min(2).max(300).describe("What to look for."),
        limit: z.number().int().min(1).max(30).optional().describe("Maximum passages (default 8)."),
      },
      annotations: readOnly,
    },
    ({ query, limit }) => call("mcp_search_knowledge", { p_key: apiKey, p_query: query, p_limit: limit ?? 8 }),
  );

  return server;
}
