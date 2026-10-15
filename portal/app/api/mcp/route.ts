import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";
import { createGenieMcpServer } from "@/lib/mcp/server";

// Genie MCP endpoint: https://genie.infiniduo.com/api/mcp (Streamable HTTP, stateless).
// Authenticate with a workspace API key from the portal, preferably as
//   Authorization: Bearer gnk_...
// For clients that cannot send headers (e.g. a custom connector URL) `?key=gnk_...` also works.

export const dynamic = "force-dynamic";

const KEY_PATTERN = /^gnk_[A-Za-z0-9_-]{20,100}$/;

function apiKeyFrom(request: Request): string | null {
  const auth = request.headers.get("authorization");
  const fromHeader = auth?.match(/^Bearer\s+(\S+)$/i)?.[1] ?? request.headers.get("x-api-key");
  const key = fromHeader ?? new URL(request.url).searchParams.get("key");
  return key && KEY_PATTERN.test(key) ? key : null;
}

function unauthorized() {
  return Response.json(
    {
      jsonrpc: "2.0",
      error: { code: -32001, message: "Missing or malformed API key. Send 'Authorization: Bearer gnk_…' (create a key in the Genie portal)." },
      id: null,
    },
    { status: 401, headers: { "WWW-Authenticate": 'Bearer realm="genie"' } },
  );
}

async function handle(request: Request) {
  const key = apiKeyFrom(request);
  if (!key) return unauthorized();

  // Stateless: a fresh server and transport per request; the key travels with every request.
  const server = createGenieMcpServer(key);
  const transport = new WebStandardStreamableHTTPServerTransport({
    sessionIdGenerator: undefined,
    enableJsonResponse: true,
  });
  await server.connect(transport);
  try {
    return await transport.handleRequest(request);
  } finally {
    // Responses are JSON (not streamed), so everything is written by now.
    void server.close();
  }
}

export const POST = handle;
export const GET = handle;
export const DELETE = handle;
