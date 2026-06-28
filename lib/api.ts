const PIPELINE_API_URL = process.env.NEXT_PUBLIC_PIPELINE_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";
const CHAT_API_URL = process.env.NEXT_PUBLIC_CHAT_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8002";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

export function saveToken(token: string) {
  localStorage.setItem("token", token);
}

export function clearToken() {
  localStorage.removeItem("token");
  localStorage.removeItem("thread_id");
}

export function isLoggedIn(): boolean {
  return !!getToken();
}

async function apiFetch(path: string, init?: RequestInit, baseUrl = PIPELINE_API_URL) {
  const token = getToken();
  const res = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (res.status === 401) {
    clearToken();
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  return res;
}

function chatFetch(path: string, init?: RequestInit) {
  return apiFetch(path, init, CHAT_API_URL);
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function login(username: string, password: string): Promise<void> {
  const res = await fetch(`${PIPELINE_API_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error("Invalid username or password");
  const data = await res.json();
  saveToken(data.access_token);
}

// ── Chat ──────────────────────────────────────────────────────────────────────

export interface Source {
  file_name: string;
  document_type?: string;
  score?: number;
  extracted_data?: Record<string, unknown>;
  image_urls?: string[];
  index?: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  streaming?: boolean;
}

export async function sendMessage(question: string, threadId: string) {
  const res = await chatFetch("/api/chat", {
    method: "POST",
    body: JSON.stringify({ question, thread_id: threadId }),
  });
  if (!res.ok) throw new Error("Chat failed");
  return res.json() as Promise<{ answer: string; sources: Source[]; thread_id: string }>;
}

export async function clearConversation(threadId: string) {
  await chatFetch(`/api/chat/conversations/${threadId}`, { method: "DELETE" });
}

export function streamMessage(
  question: string,
  threadId: string,
  onChunk: (chunk: string) => void,
  onDone: (sources: Source[], finalThreadId: string) => void,
  onError: (err: string) => void,
): () => void {
  const token = getToken();
  const params = new URLSearchParams({ question, thread_id: threadId });
  const url = `${CHAT_API_URL}/api/chat/stream?${params}`;

  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal,
      });
      if (res.status === 401) {
        clearToken();
        window.location.href = "/login";
        return;
      }
      if (!res.ok || !res.body) {
        onError(`Stream failed (${res.status})`);
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;
          const event = JSON.parse(raw);
          if (event.chunk !== undefined) onChunk(event.chunk);
          else if (event.done) onDone(event.sources ?? [], event.thread_id ?? threadId);
          else if (event.error) onError(event.error);
        }
      }
    } catch (e: unknown) {
      if (e instanceof Error && e.name !== "AbortError") onError(e.message);
    }
  })();

  return () => controller.abort();
}

export async function generateReport(
  sources: Source[],
  district = "",
  districtEn = "",
  reportType = "rent",
): Promise<Blob> {
  const token = getToken();
  const res = await fetch(`${CHAT_API_URL}/api/chat/report`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      sources,
      district,
      district_en: districtEn,
      report_type: reportType,
    }),
  });
  if (res.status === 401) {
    clearToken();
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Report generation failed");
  }
  return res.blob();
}

// ── Search ────────────────────────────────────────────────────────────────────

export async function search(query: string, topK = 20) {
  const res = await chatFetch("/api/search", {
    method: "POST",
    body: JSON.stringify({ query, top_k: topK, search_type: "keyword" }),
  });
  if (!res.ok) throw new Error("Search failed");
  return res.json();
}

// ── Admin ─────────────────────────────────────────────────────────────────────

export interface RunRecord {
  run_id: string;
  file_name: string;
  document_type: string;
  confidence: number;
  status: "success" | "error";
  extracted_data: Record<string, unknown>;
  duration_ms: number;
  processed_at: string | null;
}

export interface TokenStats {
  total: number;
  prompt: number;
  completion: number;
}

export interface DocumentRecord {
  id: string;
  file_name: string;
  document_type: string;
  processed_at: string | null;
  extracted_data: Record<string, unknown> | null;
  image_urls: string[];
  chunk_count: number;
  needs_review?: boolean;
  extraction_path?: string;
}

export interface HistoryRecord {
  row_key: string;
  file_name: string;
  document_type: string;
  status: "success" | "error";
  duration_ms: number;
  processed_at: string;
  extracted_data: Record<string, unknown>;
  error_message: string;
  index_id: string;
}

export async function getAdminHistory(months = 3, top = 500): Promise<{ runs: HistoryRecord[]; total: number }> {
  const res = await apiFetch(`/api/monitoring/history?months=${months}&top=${top}`);
  if (!res.ok) throw new Error("Failed to fetch history");
  return res.json();
}

export async function getAdminRuns(hours = 72): Promise<{ runs: RunRecord[]; token_stats: TokenStats }> {
  const res = await apiFetch(`/api/monitoring/runs?hours=${hours}`);
  if (!res.ok) throw new Error("Failed to fetch runs");
  return res.json();
}

export async function updateDocument(
  docId: string,
  extractedData: Record<string, unknown>,
  needsReview?: boolean,
): Promise<void> {
  const body: Record<string, unknown> = { extracted_data: extractedData };
  if (needsReview !== undefined) body.needs_review = needsReview;
  const res = await apiFetch(`/api/documents/${encodeURIComponent(docId)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error((detail as { detail?: string }).detail ?? "Failed to save changes");
  }
}

export async function getAdminDocuments(topK = 1000, needsReview = false): Promise<{
  total_chunks: number;
  total_files: number;
  by_type: Record<string, number>;
  files: DocumentRecord[];
}> {
  const params = new URLSearchParams({ top_k: String(topK), needs_review: String(needsReview) });
  const res = await apiFetch(`/api/documents?${params}`);
  if (!res.ok) throw new Error("Failed to fetch documents");
  return res.json();
}

export interface AdminConfig {
  inbox_folder: string;
  processed_folder: string;
  move_when_done: boolean;
  timer_enabled: boolean;
  ms_client_id: string;
  ms_tenant_id: string;
  ms_client_secret_configured: boolean;
  ms_drive_id: string;
}

export async function getAdminConfig(): Promise<AdminConfig> {
  const res = await apiFetch("/api/config");
  if (!res.ok) throw new Error("Failed to fetch config");
  return res.json();
}

export async function updateAdminConfig(
  cfg: Partial<AdminConfig & { ms_client_secret: string }>,
): Promise<AdminConfig> {
  const res = await apiFetch("/api/config", {
    method: "PUT",
    body: JSON.stringify(cfg),
  });
  if (!res.ok) throw new Error("Failed to update config");
  return res.json();
}

export interface IngestResult {
  file_name: string;
  document_type: string;
  confidence: number;
  status: "success" | "error";
  pages: number;
  tables: number;
  extracted_data: Record<string, unknown>;
  error?: string | null;
  index_id?: string;
}

export async function processIngest(file: File): Promise<{ results: IngestResult[] }> {
  const token = localStorage.getItem("token");
  const form = new FormData();
  form.append("file", file);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120_000);
  try {
    const res = await fetch(`${PIPELINE_API_URL}/api/pipeline/process`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
      signal: controller.signal,
    });
    if (res.status === 401) { clearToken(); window.location.href = "/login"; throw new Error("Unauthorized"); }
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error((detail as { detail?: string }).detail ?? "Processing failed");
    }
    return res.json();
  } catch (e: unknown) {
    if (e instanceof Error && e.name === "AbortError") throw new Error("Processing took too long — try again.");
    throw e;
  } finally {
    clearTimeout(timeout);
  }
}

export interface TriageResult {
  file_name: string;
  can_process: boolean;
  detected_type: string;
  format: string;
  confidence: number;
  reason: string | null;
}

export async function triageFile(file: File): Promise<TriageResult> {
  const token = localStorage.getItem("token");
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${PIPELINE_API_URL}/api/pipeline/triage`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (res.status === 401) {
    clearToken();
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  if (!res.ok) throw new Error(`Triage failed (${res.status})`);
  return res.json();
}

export interface OneDriveCheckResult {
  drive_configured: boolean;
  in_inbox?: boolean;
  in_processed?: boolean;
  inbox_folder?: string;
  processed_folder?: string;
}

export interface DriveRecord {
  id: string;
  name: string;
  type: string;
  is_default: boolean;
}

export async function listOneDrives(): Promise<{ drives: DriveRecord[] }> {
  const res = await apiFetch("/api/pipeline/onedrive-drives");
  if (!res.ok) return { drives: [] };
  return res.json();
}

export async function listOneDriveFolders(
  path = "/",
  driveId?: string,
): Promise<{ folders: Array<{ name: string; path: string }>; path: string }> {
  const params = new URLSearchParams({ path });
  if (driveId) params.set("drive_id", driveId);
  const res = await apiFetch(`/api/pipeline/onedrive-folders?${params}`);
  if (!res.ok) return { folders: [], path };
  return res.json();
}

export async function checkOneDrive(fileName: string): Promise<OneDriveCheckResult> {
  const token = getToken();
  const res = await fetch(
    `${PIPELINE_API_URL}/api/pipeline/onedrive-check?file_name=${encodeURIComponent(fileName)}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );
  if (res.status === 401) { clearToken(); window.location.href = "/login"; throw new Error("Unauthorized"); }
  if (!res.ok) return { drive_configured: false };
  return res.json();
}

export interface CheckResult {
  exists: boolean;
  document_type?: string;
  processed_at?: string;
  extracted_data?: Record<string, unknown>;
}

export async function checkFile(fileName: string): Promise<CheckResult> {
  const token = getToken();
  const res = await fetch(
    `${PIPELINE_API_URL}/api/pipeline/check?file_name=${encodeURIComponent(fileName)}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );
  if (res.status === 401) { clearToken(); window.location.href = "/login"; throw new Error("Unauthorized"); }
  if (!res.ok) return { exists: false };
  return res.json();
}

// ── Billing ───────────────────────────────────────────────────────────────────

export async function getCredits(): Promise<{ username: string; balance: number }> {
  const res = await apiFetch("/api/billing/credits");
  if (!res.ok) throw new Error("Failed to fetch credits");
  return res.json();
}

export async function createCheckout(pkg: "starter" | "pro" | "max"): Promise<{ url: string }> {
  const res = await apiFetch("/api/billing/checkout", {
    method: "POST",
    body: JSON.stringify({ package: pkg }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error((detail as { detail?: string }).detail ?? "Checkout failed");
  }
  return res.json();
}

export async function uploadFiles(
  files: File[],
  folderPath?: string,
  driveId?: string,
): Promise<{ results: Array<{ name: string; ok: boolean; error?: string; web_url?: string }>; folder: string }> {
  const token = localStorage.getItem("token");
  const form = new FormData();
  for (const f of files) form.append("files", f);
  if (folderPath) form.append("folder_path", folderPath);
  if (driveId) form.append("drive_id", driveId);
  const res = await fetch(`${PIPELINE_API_URL}/api/pipeline/upload`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (res.status === 401) {
    clearToken();
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? "Upload failed");
  }
  return res.json();
}
