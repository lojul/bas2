"use client";

import { useEffect, useState } from "react";
import { getAdminRuns, getAdminHistory } from "@/lib/api";
import type { RunRecord, TokenStats, HistoryRecord } from "@/lib/api";

const PAGE_SIZE = 20;

const DOC_TYPE_LABELS: Record<string, string> = {
  listing: "Single Listing",
  listing_list: "Multi Listing",
  pitching_deck: "Pitching Deck",
  news: "News",
  contact: "Contact",
  unknown: "Unknown",
};

function fmtDate(iso: string | null) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-HK", {
      timeZone: "Asia/Hong_Kong",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return iso.slice(0, 16);
  }
}

function fmtDuration(ms: number) {
  if (!ms) return "—";
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

function groupByFile(runs: RunRecord[]): RunRecord[] {
  const map = new Map<string, RunRecord>();
  for (const r of runs) {
    const existing = map.get(r.file_name);
    if (!existing) {
      map.set(r.file_name, { ...r, run_count: 1 } as RunRecord & { run_count: number });
    } else {
      (existing as RunRecord & { run_count: number }).run_count++;
      if (existing.document_type === "unknown" && r.document_type !== "unknown") {
        existing.document_type = r.document_type;
        existing.confidence = r.confidence;
        existing.extracted_data = r.extracted_data;
      }
    }
  }
  return Array.from(map.values());
}

// ── Recent tab (LangSmith) ────────────────────────────────────────────────────

function RecentTab() {
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [tokenStats, setTokenStats] = useState<TokenStats>({ total: 0, prompt: 0, completion: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [page, setPage] = useState(0);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    getAdminRuns(72)
      .then((data) => { setRuns(data.runs); setTokenStats(data.token_stats); })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const grouped = groupByFile(runs);
  const total = runs.length;
  const successCount = runs.filter((r) => r.status === "success").length;
  const errorCount = total - successCount;
  const successRate = total > 0 ? Math.round((successCount / total) * 100) : 100;
  const COST_PER_1M_INPUT = 0.14;
  const COST_PER_1M_OUTPUT = 0.28;
  const estCost =
    (tokenStats.prompt / 1_000_000) * COST_PER_1M_INPUT +
    (tokenStats.completion / 1_000_000) * COST_PER_1M_OUTPUT;
  const totalPages = Math.ceil(grouped.length / PAGE_SIZE);
  const pageItems = grouped.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  function toggleExpand(id: string) {
    setExpanded((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }

  if (loading) return <p className="text-sm text-gray-500 p-4">Loading…</p>;
  if (error) return <p className="text-sm text-red-600 p-4">{error}</p>;

  return (
    <>
      <div className="grid grid-cols-3 lg:grid-cols-6 gap-3 mb-4">
        {[
          { label: "Total Processed", value: total },
          { label: "Successes", value: successCount },
          { label: "Success Rate", value: `${successRate}%` },
          { label: "Errors", value: errorCount },
          { label: "Total Tokens", value: tokenStats.total.toLocaleString() },
          { label: "Est. Cost", value: `$${estCost.toFixed(4)}` },
        ].map(({ label, value }) => (
          <div key={label} className="bg-white rounded-xl border border-gray-200 px-4 py-3">
            <p className="text-xs text-gray-500">{label}</p>
            <p className="text-lg font-semibold text-gray-900 mt-0.5">{value}</p>
          </div>
        ))}
      </div>

      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="grid grid-cols-[2fr_1fr_0.6fr_0.8fr_0.5fr] gap-2 px-4 py-2 border-b border-gray-100 text-xs font-medium text-gray-500 uppercase tracking-wide">
          <span>File</span><span>Type</span><span>Status</span><span>Date (HKT)</span><span>Data</span>
        </div>
        {pageItems.length === 0 && <p className="text-sm text-gray-400 px-4 py-6">No runs found</p>}
        {pageItems.map((run) => {
          const isOpen = expanded.has(run.run_id);
          const rc = (run as RunRecord & { run_count?: number }).run_count;
          return (
            <div key={run.run_id} className="border-b border-gray-50 last:border-0">
              <div className="grid grid-cols-[2fr_1fr_0.6fr_0.8fr_0.5fr] gap-2 px-4 py-3 text-sm items-center hover:bg-gray-50">
                <div className="truncate">
                  <span className="text-gray-800">{run.file_name}</span>
                  {rc && rc > 1 && <span className="ml-1.5 text-xs text-gray-400">×{rc}</span>}
                </div>
                <span className="text-gray-600 text-xs">{DOC_TYPE_LABELS[run.document_type] ?? run.document_type}</span>
                <span className={`text-xs font-medium ${run.status === "success" ? "text-green-600" : "text-red-500"}`}>
                  {run.status === "success" ? "OK" : "ERR"}
                </span>
                <span className="text-gray-500 text-xs">{fmtDate(run.processed_at)}</span>
                <div>
                  {Object.keys(run.extracted_data ?? {}).length > 0 ? (
                    <button onClick={() => toggleExpand(run.run_id)} className="text-xs text-blue-600 hover:underline">
                      {isOpen ? "Hide" : "View"}
                    </button>
                  ) : <span className="text-gray-300 text-xs">—</span>}
                </div>
              </div>
              {isOpen && (
                <div className="px-4 pb-3 bg-gray-50">
                  <pre className="text-xs text-gray-700 bg-white border border-gray-200 rounded-lg p-3 overflow-x-auto max-h-64">
                    {JSON.stringify(run.extracted_data, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-3 text-sm text-gray-500">
          <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}
            className="px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-100 disabled:opacity-40">← Prev</button>
          <span>Page {page + 1} of {totalPages} ({grouped.length} files)</span>
          <button onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}
            className="px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-100 disabled:opacity-40">Next →</button>
        </div>
      )}
    </>
  );
}

// ── History tab (Azure Table Storage) ────────────────────────────────────────

function HistoryTab() {
  const [runs, setRuns] = useState<HistoryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [page, setPage] = useState(0);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    getAdminHistory(3, 500)
      .then((data) => setRuns(data.runs))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const total = runs.length;
  const successCount = runs.filter((r) => r.status === "success").length;
  const errorCount = total - successCount;
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const pageItems = runs.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  function toggleExpand(id: string) {
    setExpanded((prev) => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }

  if (loading) return <p className="text-sm text-gray-500 p-4">Loading…</p>;
  if (error) return <p className="text-sm text-red-600 p-4">{error}</p>;

  return (
    <>
      <div className="grid grid-cols-3 gap-3 mb-4">
        {[
          { label: "Total (3 months)", value: total },
          { label: "Successes", value: successCount },
          { label: "Errors", value: errorCount },
        ].map(({ label, value }) => (
          <div key={label} className="bg-white rounded-xl border border-gray-200 px-4 py-3">
            <p className="text-xs text-gray-500">{label}</p>
            <p className="text-lg font-semibold text-gray-900 mt-0.5">{value}</p>
          </div>
        ))}
      </div>

      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="grid grid-cols-[2fr_1fr_0.6fr_0.6fr_0.8fr_0.5fr] gap-2 px-4 py-2 border-b border-gray-100 text-xs font-medium text-gray-500 uppercase tracking-wide">
          <span>File</span><span>Type</span><span>Status</span><span>Duration</span><span>Date (HKT)</span><span>Data</span>
        </div>
        {pageItems.length === 0 && <p className="text-sm text-gray-400 px-4 py-6">No history yet — records appear after the next document is processed</p>}
        {pageItems.map((run) => {
          const isOpen = expanded.has(run.row_key);
          return (
            <div key={run.row_key} className="border-b border-gray-50 last:border-0">
              <div className="grid grid-cols-[2fr_1fr_0.6fr_0.6fr_0.8fr_0.5fr] gap-2 px-4 py-3 text-sm items-center hover:bg-gray-50">
                <div className="truncate">
                  <span className="text-gray-800">{run.file_name}</span>
                </div>
                <span className="text-gray-600 text-xs">{DOC_TYPE_LABELS[run.document_type] ?? run.document_type}</span>
                <span className={`text-xs font-medium ${run.status === "success" ? "text-green-600" : "text-red-500"}`}>
                  {run.status === "success" ? "OK" : "ERR"}
                </span>
                <span className="text-gray-400 text-xs">{fmtDuration(run.duration_ms)}</span>
                <span className="text-gray-500 text-xs">{fmtDate(run.processed_at)}</span>
                <div>
                  {run.status === "error" && run.error_message ? (
                    <button onClick={() => toggleExpand(run.row_key)} className="text-xs text-red-500 hover:underline">
                      {isOpen ? "Hide" : "Error"}
                    </button>
                  ) : Object.keys(run.extracted_data ?? {}).length > 0 ? (
                    <button onClick={() => toggleExpand(run.row_key)} className="text-xs text-blue-600 hover:underline">
                      {isOpen ? "Hide" : "View"}
                    </button>
                  ) : <span className="text-gray-300 text-xs">—</span>}
                </div>
              </div>
              {isOpen && (
                <div className="px-4 pb-3 bg-gray-50">
                  <pre className="text-xs text-gray-700 bg-white border border-gray-200 rounded-lg p-3 overflow-x-auto max-h-64">
                    {run.status === "error"
                      ? run.error_message
                      : JSON.stringify(run.extracted_data, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-3 text-sm text-gray-500">
          <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}
            className="px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-100 disabled:opacity-40">← Prev</button>
          <span>Page {page + 1} of {totalPages} ({total} runs)</span>
          <button onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}
            className="px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-100 disabled:opacity-40">Next →</button>
        </div>
      )}
    </>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ProcessPage() {
  const [activeTab, setActiveTab] = useState<"recent" | "history">("recent");

  return (
    <div className="flex flex-col h-full bg-gray-50">
      <header className="px-6 py-3 bg-white border-b border-gray-200 shrink-0">
        <p className="text-sm font-medium text-gray-700">Processing</p>
        <p className="text-xs text-gray-400">
          {activeTab === "recent" ? "LangSmith traces — last 72 hours" : "Azure Table Storage — permanent history"}
        </p>
      </header>

      <div className="px-6 pt-4 bg-gray-50 shrink-0">
        <div className="flex gap-1 bg-gray-200 rounded-lg p-1 w-fit">
          {(["recent", "history"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                activeTab === tab ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {tab === "recent" ? "Recent (72h)" : "History (All Time)"}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {activeTab === "recent" ? <RecentTab /> : <HistoryTab />}
      </div>
    </div>
  );
}
