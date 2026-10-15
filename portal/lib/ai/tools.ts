// The agent's tools. Same names and behaviour as the MCP server's tools; executed through the
// agent_tool() database function as the signed-in member (shared/ migration 20261015000800).

export type ToolSpec = {
  name: string;
  description: string;
  input_schema: { type: "object"; properties: Record<string, unknown>; required?: string[]; additionalProperties: false };
};

export const AGENT_TOOLS: ToolSpec[] = [
  {
    name: "workspace_info",
    description: "The workspace's connected data sources and the record types it holds, with counts. Call this first when unsure what data exists.",
    input_schema: { type: "object", properties: {}, additionalProperties: false },
  },
  {
    name: "search_records",
    description:
      "Keyword search over the company's synced records (contacts, products, sales orders, listings, policies, ...). " +
      "Matches titles, text and field values, including Chinese. Optionally limit to one object_type from workspace_info. " +
      "Returns id, type, title and a snippet; call get_record for all fields.",
    input_schema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Words to look for. Omit to list the most recent records." },
        object_type: { type: "string", description: "Only this record type, e.g. 'product' or 'sales_order'." },
        limit: { type: "integer", minimum: 1, maximum: 50, description: "Maximum results (default 10)." },
      },
      additionalProperties: false,
    },
  },
  {
    name: "get_record",
    description: "All fields of one record, by the id from search_records or find_contact.",
    input_schema: {
      type: "object",
      properties: { id: { type: "string", description: "Record id (UUID)." } },
      required: ["id"],
      additionalProperties: false,
    },
  },
  {
    name: "find_contact",
    description: "Find people and companies by name, company, email or phone number (matched on digits).",
    input_schema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Name, company, email or phone number." },
        limit: { type: "integer", minimum: 1, maximum: 50 },
      },
      required: ["query"],
      additionalProperties: false,
    },
  },
  {
    name: "search_knowledge",
    description: "Search passages of policies, procedures and uploaded documents. Use for 'what is our policy on…' or 'how do we…' questions.",
    input_schema: {
      type: "object",
      properties: {
        query: { type: "string", description: "What to look for." },
        limit: { type: "integer", minimum: 1, maximum: 30 },
      },
      required: ["query"],
      additionalProperties: false,
    },
  },
];

export const TOOL_NAMES = new Set(AGENT_TOOLS.map((t) => t.name));
