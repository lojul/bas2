import "server-only";

// A customer's own Azure AI Search index, read live with a query key (read-only by design: query
// keys can only search and look up documents). Nothing is stored in Genie.
//
// Ranking: keyword + Azure's semantic reranker when the index has a semantic configuration; plus a
// vector query when the index has a vectorizer for its vector field (C21's properties-index has
// none yet, so that part switches itself off until one is added).

const API = "2024-07-01";

export type SearchConfig = { endpoint: string; index: string; semantic?: string | null; vectorField?: string | null };
export type LiveSearch = SearchConfig & { name: string; key: string };

type Doc = Record<string, unknown> & { "@search.captions"?: { text?: string }[]; "@search.rerankerScore"?: number };

// Remembered per index for this server instance, so a missing feature costs one failed call.
const unsupported = new Map<string, Set<"semantic" | "vector">>();

export function normaliseSearchEndpoint(raw: string): string {
  const v = raw.trim();
  const u = new URL(v.startsWith("http") ? v : `https://${v}`);
  if (u.protocol !== "https:") throw new Error("Use an https:// address.");
  return u.origin;
}

async function post(live: Pick<LiveSearch, "endpoint" | "index" | "key">, body: Record<string, unknown>) {
  const res = await fetch(`${live.endpoint}/indexes/${encodeURIComponent(live.index)}/docs/search?api-version=${API}`, {
    method: "POST",
    headers: { "api-key": live.key, "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const json = (await res.json().catch(() => null)) as { value?: Doc[]; "@odata.count"?: number; error?: { message?: string } } | null;
  if (!res.ok) {
    const msg = json?.error?.message ?? `HTTP ${res.status}`;
    if (res.status === 403 || res.status === 401) throw new SearchError(`The search service refused the key (${msg}).`, "auth");
    if (res.status === 404) throw new SearchError(`Index "${live.index}" not found on ${live.endpoint}.`, "notfound");
    throw new SearchError(msg, "bad");
  }
  return json ?? {};
}

export class SearchError extends Error {
  constructor(
    message: string,
    public kind: "auth" | "notfound" | "bad",
  ) {
    super(message);
  }
}

// Turn-on check: one tiny search with the given details.
export async function testSearch(cfg: SearchConfig & { key: string }) {
  const r = await post(cfg, { search: "*", top: 1, count: true });
  return { count: r["@odata.count"] ?? null };
}

async function search(live: LiveSearch, query: string, top: number, filter?: string) {
  const key = `${live.endpoint}|${live.index}`;
  const off = unsupported.get(key) ?? new Set();
  const useSemantic = !!live.semantic && !off.has("semantic");
  const useVector = !!live.vectorField && !off.has("vector");
  const body: Record<string, unknown> = { search: query || "*", top, count: true, ...(filter ? { filter } : {}) };
  if (useSemantic) Object.assign(body, { queryType: "semantic", semanticConfiguration: live.semantic, captions: "extractive" });
  if (useVector && query) body.vectorQueries = [{ kind: "text", text: query, fields: live.vectorField, k: Math.max(top * 3, 20) }];
  try {
    return await post(live, body);
  } catch (e) {
    if (!(e instanceof SearchError) || e.kind !== "bad") throw e;
    // Fall back once: drop the vector part (no vectorizer), then the semantic part.
    if (useVector) off.add("vector");
    else if (useSemantic) off.add("semantic");
    else throw e;
    unsupported.set(key, off);
    return search(live, query, top, filter);
  }
}

const HIDDEN = /^(@|content$|contentVector$|.*[Vv]ector$|id$)/;
const LINK_FIELDS = ["sourceWebUrl", "url", "webUrl", "link"];
const TITLE_FIELDS = ["title", "address", "name", "fileName", "sourceBlob"];

function titleOf(d: Doc) {
  for (const f of TITLE_FIELDS) if (typeof d[f] === "string" && d[f]) return String(d[f]).split("/").pop()!.slice(0, 200);
  return String(d.id ?? "(untitled)");
}
function linkOf(d: Doc) {
  for (const f of LINK_FIELDS) if (typeof d[f] === "string" && d[f]) return String(d[f]);
  return null;
}
function facts(d: Doc) {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(d)) {
    if (HIDDEN.test(k) || LINK_FIELDS.includes(k) || TITLE_FIELDS.includes(k)) continue;
    if (v === null || v === "" || (Array.isArray(v) && v.length === 0)) continue;
    if (typeof v === "object" && !Array.isArray(v)) continue;
    out[k] = Array.isArray(v) ? v.slice(0, 10) : v;
  }
  return out;
}

export async function liveSearchKnowledge(live: LiveSearch, query: string, limit: number) {
  const r = await search(live, query, limit);
  return {
    source: live.name,
    total_matches: r["@odata.count"] ?? null,
    results: (r.value ?? []).map((d) => ({
      id: `search:${d.id}`,
      title: titleOf(d),
      snippet: (d["@search.captions"]?.[0]?.text ?? String(d.content ?? "")).replace(/\s+/g, " ").slice(0, 400),
      facts: facts(d),
      link: linkOf(d),
    })),
  };
}

export async function liveGetDocument(live: LiveSearch, id: string) {
  const key = id.replace(/^search:/, "");
  const res = await fetch(
    `${live.endpoint}/indexes/${encodeURIComponent(live.index)}/docs/${encodeURIComponent(key)}?api-version=${API}`,
    { headers: { "api-key": live.key }, cache: "no-store" },
  );
  if (res.status === 404) return { found: false, id };
  if (!res.ok) throw new SearchError(`Search service returned HTTP ${res.status}`, "bad");
  const d = (await res.json()) as Doc;
  return {
    id,
    title: titleOf(d),
    facts: facts(d),
    text: String(d.content ?? "").replace(/\s+/g, " ").slice(0, 6000),
    link: linkOf(d),
  };
}

export async function liveIndexInfo(live: LiveSearch) {
  const r = await post(live, { search: "*", top: 0, count: true });
  return { name: live.name, kind: "Search index (read live, nothing stored in Genie)", documents: r["@odata.count"] ?? null };
}
