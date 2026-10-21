import "server-only";

// Minimal Odoo external-API client. Odoo 19+ uses JSON-2 (POST /json/2/<model>/<method>,
// bearer API key); older versions use the legacy JSON-RPC endpoint (/jsonrpc, execute_kw),
// which needs the user's login as well. A key made with Scope "MCP" (Odoo 20) only works on
// Odoo's MCP server (/mcp), which can search and count but not write. `connect` picks whichever
// the server answers.

export type OdooConfig = { url: string; db: string; login?: string; apiKey: string };
export type OdooMode = "json2" | "jsonrpc" | "mcp";

export class OdooError extends Error {}
class KeyRefused extends OdooError {}

// The source kind saved in the sources table for each mode, and back.
const KIND: Record<OdooMode, string> = { json2: "odoo_json2", jsonrpc: "odoo_xmlrpc", mcp: "odoo_mcp" };
export const kindOfMode = (mode: OdooMode) => KIND[mode];
export const modeOfKind = (kind: string): OdooMode => (kind === "odoo_json2" ? "json2" : kind === "odoo_mcp" ? "mcp" : "jsonrpc");

export class OdooClient {
  private uid: number | null = null;
  constructor(
    private cfg: OdooConfig,
    public mode: OdooMode,
  ) {}

  static async connect(cfg: OdooConfig): Promise<OdooClient> {
    const json2 = new OdooClient(cfg, "json2");
    let refused: KeyRefused | null = null;
    try {
      await json2.call("res.users", "context_get", {});
      return json2;
    } catch (e) {
      if (e instanceof KeyRefused) refused = e;
      else if (!(e instanceof NotJson2)) throw e;
    }
    // JSON-2 refuses an MCP-scoped key (and answers 404 to a wrong database name); try /mcp.
    const mcp = new OdooClient(cfg, "mcp");
    try {
      await mcp.call("res.users", "context_get", {});
      return mcp;
    } catch (e) {
      // Not an MCP key, or this Odoo has no MCP server.
      if (e instanceof KeyRefused) refused ??= e;
    }
    if (refused) throw refused;
    if (!cfg.login) {
      throw new OdooError("This Odoo does not offer the JSON-2 API (Odoo 19+). Enter the login email to use the older API.");
    }
    const legacy = new OdooClient(cfg, "jsonrpc");
    await legacy.login();
    return legacy;
  }

  // A client for a source already checked at connect time: JSON-2 needs no handshake; the older
  // API still has to log in for its user id.
  static async open(cfg: OdooConfig, mode: OdooMode): Promise<OdooClient> {
    if (mode !== "jsonrpc") return new OdooClient(cfg, mode);
    const legacy = new OdooClient(cfg, "jsonrpc");
    await legacy.login();
    return legacy;
  }

  async call<T = unknown>(model: string, method: string, kwargs: Record<string, unknown>): Promise<T> {
    if (this.mode === "mcp") return this.callMcp<T>(model, method, kwargs);
    return this.mode === "json2" ? this.callJson2<T>(model, method, kwargs) : this.callJsonRpc<T>(model, method, kwargs);
  }

  // Odoo's MCP server offers tools, not model methods: map the few methods Genie reads with onto
  // them and return what JSON-2 would. Anything else (writes) is not possible with an MCP key.
  private async callMcp<T>(model: string, method: string, kwargs: Record<string, unknown>): Promise<T> {
    if (method === "context_get") {
      await this.mcpTool("ai_tool_mcp_retrieve_initial_context", {});
      return {} as T;
    }
    if (method === "fields_get") {
      const { response } = await this.mcpTool<{ response: string }>("ai_tool_get_fields", { model_name: model, include_description: false });
      return parseMcpFields(response) as T;
    }
    if (method === "search_read" || method === "search_count") {
      const count = method === "search_count";
      const { response } = await this.mcpTool<{ response: { records: unknown[]; total_count: number } }>("ai_tool_search", {
        model_name: model,
        domain: pyLiteral(kwargs.domain ?? []),
        fields: count ? ["id"] : (kwargs.fields ?? ["display_name"]),
        limit: count ? 1 : Math.min(Number(kwargs.limit ?? 50), 200),
        ...(kwargs.order && !count ? { order: kwargs.order } : {}),
      });
      return (count ? response.total_count : response.records) as T;
    }
    throw new OdooError(`Odoo ${model}.${method}: not possible with an MCP key (it can only read). Use a key with Scope "RPC".`);
  }

  private async mcpTool<T>(name: string, args: Record<string, unknown>): Promise<T> {
    // No X-Odoo-Database header: Odoo picks the database from the address, and a wrong name breaks /mcp.
    const res = await fetch(`${this.cfg.url}/mcp`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.cfg.apiKey}`,
        "Content-Type": "application/json",
        Accept: "application/json, text/event-stream",
      },
      body: JSON.stringify({ jsonrpc: "2.0", id: Date.now(), method: "tools/call", params: { name, arguments: args } }),
      cache: "no-store",
    });
    if (res.status === 401) throw new KeyRefused("Odoo refused the API key.");
    let text = await res.text();
    // Streamable HTTP may answer as server-sent events: the JSON is on the "data:" line.
    if ((res.headers.get("content-type") ?? "").includes("text/event-stream")) {
      text = text.split("\n").filter((l) => l.startsWith("data:")).map((l) => l.slice(5)).join("");
    }
    let body: { result?: { content?: { text?: string }[]; isError?: boolean }; error?: { message?: string } };
    try {
      body = JSON.parse(text);
    } catch {
      throw new OdooError(`Odoo's MCP server did not answer (HTTP ${res.status}).`);
    }
    if (body.error) throw new OdooError(`Odoo MCP: ${body.error.message ?? "error"}`);
    const out = body.result?.content?.[0]?.text ?? "";
    let parsed: unknown = out;
    try {
      parsed = JSON.parse(out);
    } catch {
      // Plain text (e.g. the initial context).
    }
    if (body.result?.isError) {
      const msg = typeof parsed === "string" ? parsed : out;
      throw new OdooError(`Odoo ${String(args.model_name ?? name)}: ${msg.replace(/\s+while evaluating[\s\S]*$/, "").slice(0, 300)}`);
    }
    return parsed as T;
  }

  private async callJson2<T>(model: string, method: string, kwargs: Record<string, unknown>): Promise<T> {
    const res = await fetch(`${this.cfg.url}/json/2/${model}/${method}`, {
      method: "POST",
      headers: {
        Authorization: `bearer ${this.cfg.apiKey}`,
        "X-Odoo-Database": this.cfg.db,
        "Content-Type": "application/json; charset=utf-8",
      },
      body: JSON.stringify(kwargs),
      cache: "no-store",
    });
    if (res.status === 404 && !(res.headers.get("content-type") ?? "").includes("json")) throw new NotJson2();
    const body = await res.json().catch(() => null);
    if (!res.ok) {
      const msg = (body as { message?: string } | null)?.message ?? `HTTP ${res.status}`;
      if (res.status === 401) throw new KeyRefused(`Odoo refused the API key (${msg}).`);
      throw new OdooError(`Odoo ${model}.${method}: ${msg}`);
    }
    return body as T;
  }

  private async rpc<T>(service: string, method: string, args: unknown[]): Promise<T> {
    const res = await fetch(`${this.cfg.url}/jsonrpc`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: { service, method, args }, id: Date.now() }),
      cache: "no-store",
    });
    if (!res.ok) throw new OdooError(`Odoo returned HTTP ${res.status}`);
    const body = (await res.json()) as { result?: T; error?: { data?: { message?: string }; message?: string } };
    if (body.error) throw new OdooError(body.error.data?.message ?? body.error.message ?? "Odoo error");
    return body.result as T;
  }

  private async login() {
    const uid = await this.rpc<number | false>("common", "login", [this.cfg.db, this.cfg.login, this.cfg.apiKey]);
    if (!uid) throw new OdooError("Odoo refused the login or API key.");
    this.uid = uid;
  }

  private callJsonRpc<T>(model: string, method: string, kwargs: Record<string, unknown>) {
    return this.rpc<T>("object", "execute_kw", [this.cfg.db, this.uid, this.cfg.apiKey, model, method, [], kwargs]);
  }
}

class NotJson2 extends Error {}

// MCP tools take the domain as text that Odoo reads as a Python literal (True/False/None, not JSON's).
function pyLiteral(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(pyLiteral).join(", ")}]`;
  if (v === true) return "True";
  if (v === false) return "False";
  if (v === null || v === undefined) return "None";
  return JSON.stringify(v);
}

// ai_tool_get_fields answers with a table: "field_name|display_name|type|sortable|groupable|readonly|dependencies",
// where type looks like "char", "many2one(res.partner)" or "selection({'a': 'A', 'b': 'B'})".
// Shaped like fields_get; "sortable" stands in for "stored", which the table doesn't give.
function parseMcpFields(table: string) {
  const fields: Record<string, { type: string; string: string; store: boolean; selection?: [string, string][] }> = {};
  for (const line of table.split("\n").slice(1)) {
    const [name, label, rawType, sortable] = line.split("|");
    if (!name || !rawType) continue;
    const type = rawType.replace(/\(.*$/, "");
    const selection =
      type === "selection" ? [...rawType.matchAll(/'((?:[^'\\]|\\.)*)':\s*'((?:[^'\\]|\\.)*)'/g)].map((m) => [m[1], m[2]] as [string, string]) : undefined;
    fields[name] = { type, string: label ?? name, store: sortable === "true", ...(selection ? { selection } : {}) };
  }
  return fields;
}

export function normaliseUrl(raw: string): string {
  const u = new URL(raw.trim().startsWith("http") ? raw.trim() : `https://${raw.trim()}`);
  if (u.protocol !== "https:") throw new OdooError("Use an https:// address.");
  return u.origin;
}
