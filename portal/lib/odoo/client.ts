import "server-only";

// Minimal Odoo external-API client. Odoo 19+ uses JSON-2 (POST /json/2/<model>/<method>,
// bearer API key); older versions use the legacy JSON-RPC endpoint (/jsonrpc, execute_kw),
// which needs the user's login as well. `connect` picks whichever the server answers.

export type OdooConfig = { url: string; db: string; login?: string; apiKey: string };
export type OdooMode = "json2" | "jsonrpc";

export class OdooError extends Error {}

export class OdooClient {
  private uid: number | null = null;
  constructor(
    private cfg: OdooConfig,
    public mode: OdooMode,
  ) {}

  static async connect(cfg: OdooConfig): Promise<OdooClient> {
    const json2 = new OdooClient(cfg, "json2");
    try {
      await json2.call("res.users", "context_get", {});
      return json2;
    } catch (e) {
      if (!(e instanceof NotJson2)) throw e;
    }
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
    if (mode === "json2") return new OdooClient(cfg, "json2");
    const legacy = new OdooClient(cfg, "jsonrpc");
    await legacy.login();
    return legacy;
  }

  async call<T = unknown>(model: string, method: string, kwargs: Record<string, unknown>): Promise<T> {
    return this.mode === "json2" ? this.callJson2<T>(model, method, kwargs) : this.callJsonRpc<T>(model, method, kwargs);
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
      if (res.status === 401) throw new OdooError(`Odoo refused the API key (${msg}).`);
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

export function normaliseUrl(raw: string): string {
  const u = new URL(raw.trim().startsWith("http") ? raw.trim() : `https://${raw.trim()}`);
  if (u.protocol !== "https:") throw new OdooError("Use an https:// address.");
  return u.origin;
}
