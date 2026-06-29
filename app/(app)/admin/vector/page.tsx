"use client";

import { useCallback, useEffect, useState } from "react";
import { getAdminDocuments, updateDocument } from "@/lib/api";
import type { DocumentRecord } from "@/lib/api";

const PAGE_SIZE = 20;

const DOC_TYPE_LABELS: Record<string, string> = {
  listing: "Single Listing",
  listing_list: "Multi Listing",
  pitching_deck: "Pitching Deck",
  news: "News",
  contact: "Contact",
  unknown: "Unknown",
};

const PATH_LABELS: Record<string, string> = {
  structured: "Structured",
  conversational: "Conversational",
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

// ── All Documents tab ──────────────────────────────────────────────────────────

function AllDocumentsTab() {
  const [files, setFiles] = useState<DocumentRecord[]>([]);
  const [byType, setByType] = useState<Record<string, number>>({});
  const [totalChunks, setTotalChunks] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filterType, setFilterType] = useState("All");
  const [page, setPage] = useState(0);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    getAdminDocuments()
      .then((data) => {
        setFiles(data.files);
        setByType(data.by_type);
        setTotalChunks(data.total_chunks);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered =
    filterType === "All" ? files : files.filter((f) => f.document_type === filterType);
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const pageItems = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  function handleFilterChange(t: string) {
    setFilterType(t);
    setPage(0);
  }

  function toggleExpand(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  if (loading) return <p className="text-sm text-gray-500 px-6 py-4">Loading…</p>;
  if (error) return <p className="text-sm text-red-600 px-6 py-4">{error}</p>;

  return (
    <div className="px-6 py-4">
      {/* Stats */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-white rounded-xl border border-gray-200 px-4 py-3">
          <p className="text-xs text-gray-500">Total Files</p>
          <p className="text-lg font-semibold text-gray-900 mt-0.5">{files.length}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 px-4 py-3">
          <p className="text-xs text-gray-500">Total Chunks</p>
          <p className="text-lg font-semibold text-gray-900 mt-0.5">{totalChunks}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 px-4 py-3">
          <p className="text-xs text-gray-500">Avg Chunks/File</p>
          <p className="text-lg font-semibold text-gray-900 mt-0.5">
            {files.length > 0 ? (totalChunks / files.length).toFixed(1) : "0"}
          </p>
        </div>
      </div>

      {/* Type breakdown */}
      {Object.keys(byType).length > 0 && (
        <div className="flex gap-3 mb-4 flex-wrap">
          {Object.entries(byType).map(([dtype, count]) => (
            <div
              key={dtype}
              className="bg-white rounded-xl border border-gray-200 px-4 py-2.5 text-center min-w-[100px]"
            >
              <p className="text-xs text-gray-500">{DOC_TYPE_LABELS[dtype] ?? dtype}</p>
              <p className="text-base font-semibold text-gray-900">{count}</p>
            </div>
          ))}
        </div>
      )}

      {/* Filter */}
      <div className="flex items-center gap-3 mb-3">
        <label className="text-xs text-gray-500">Filter by type:</label>
        <select
          value={filterType}
          onChange={(e) => handleFilterChange(e.target.value)}
          className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
        >
          <option value="All">All</option>
          {Object.keys(byType).map((dtype) => (
            <option key={dtype} value={dtype}>
              {DOC_TYPE_LABELS[dtype] ?? dtype}
            </option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="grid grid-cols-[2fr_1fr_0.5fr_0.8fr_0.5fr] gap-2 px-4 py-2 border-b border-gray-100 text-xs font-medium text-gray-500 uppercase tracking-wide">
          <span>File</span>
          <span>Type</span>
          <span>Chunks</span>
          <span>Indexed (HKT)</span>
          <span>Data</span>
        </div>

        {pageItems.length === 0 && (
          <p className="text-sm text-gray-400 px-4 py-6">No documents found</p>
        )}

        {pageItems.map((doc) => {
          const isOpen = expanded.has(doc.id ?? doc.file_name);
          const hasData = doc.extracted_data && Object.keys(doc.extracted_data).length > 0;
          return (
            <div key={doc.id ?? doc.file_name} className="border-b border-gray-50 last:border-0">
              <div className="grid grid-cols-[2fr_1fr_0.5fr_0.8fr_0.5fr] gap-2 px-4 py-3 text-sm items-center hover:bg-gray-50">
                <span className="truncate text-gray-800 flex items-center gap-1.5">
                  {doc.needs_review && (
                    <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" title="Needs review" />
                  )}
                  {doc.file_name}
                </span>
                <span className="text-gray-600 text-xs">
                  {DOC_TYPE_LABELS[doc.document_type] ?? doc.document_type}
                </span>
                <span className="text-gray-600 text-xs">{doc.chunk_count}</span>
                <span className="text-gray-500 text-xs">{fmtDate(doc.processed_at)}</span>
                <div>
                  {hasData ? (
                    <button
                      onClick={() => toggleExpand(doc.id ?? doc.file_name)}
                      className="text-xs text-blue-600 hover:underline"
                    >
                      {isOpen ? "Hide" : "View"}
                    </button>
                  ) : (
                    <span className="text-gray-300 text-xs">—</span>
                  )}
                </div>
              </div>
              {isOpen && (
                <div className="px-4 pb-3 bg-gray-50">
                  {doc.image_urls.length > 0 && (
                    <div className="flex gap-2 mb-2 flex-wrap">
                      {doc.image_urls.slice(0, 4).map((url, i) => (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          key={i}
                          src={url}
                          alt={`${doc.file_name} image ${i + 1}`}
                          className="h-16 w-auto rounded border border-gray-200 object-cover"
                        />
                      ))}
                    </div>
                  )}
                  <pre className="text-xs text-gray-700 bg-white border border-gray-200 rounded-lg p-3 overflow-x-auto max-h-64">
                    {JSON.stringify(doc.extracted_data, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-3 text-sm text-gray-500">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-100 disabled:opacity-40"
          >
            ← Prev
          </button>
          <span>
            Page {page + 1} of {totalPages} ({filtered.length} files)
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            className="px-3 py-1.5 rounded-lg border border-gray-200 hover:bg-gray-100 disabled:opacity-40"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}

// ── Review Queue tab ───────────────────────────────────────────────────────────

function ReviewQueueTab() {
  const [docs, setDocs] = useState<DocumentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [editJson, setEditJson] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    getAdminDocuments(1000, true)
      .then((data) => setDocs(data.files))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  function openReview(doc: DocumentRecord) {
    setExpanded(doc.id ?? doc.file_name);
    setEditJson(JSON.stringify(doc.extracted_data ?? {}, null, 2));
    setSaveError("");
  }

  function closeReview() {
    setExpanded(null);
    setSaveError("");
  }

  async function handleApprove(doc: DocumentRecord) {
    setSaving(true);
    setSaveError("");
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(editJson);
    } catch {
      setSaveError("Invalid JSON — fix the syntax and try again.");
      setSaving(false);
      return;
    }
    try {
      await updateDocument(doc.id, parsed, false);
      setDocs((prev) => prev.filter((d) => d.id !== doc.id));
      setExpanded(null);
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <p className="text-sm text-gray-500 px-6 py-4">Loading…</p>;
  if (error) return <p className="text-sm text-red-600 px-6 py-4">{error}</p>;

  if (docs.length === 0) {
    return (
      <div className="px-6 py-12 text-center">
        <p className="text-2xl mb-2">✓</p>
        <p className="text-sm font-medium text-gray-700">Review queue is empty</p>
        <p className="text-xs text-gray-400 mt-1">All conversational extractions met the confidence threshold.</p>
      </div>
    );
  }

  return (
    <div className="px-6 py-4 space-y-3">
      <p className="text-xs text-gray-500">
        {docs.length} document{docs.length !== 1 ? "s" : ""} flagged for review — AI confidence was below 75%.
        Correct any errors in the JSON, then click <strong>Approve</strong> to clear the flag.
      </p>

      {docs.map((doc) => {
        const isOpen = expanded === (doc.id ?? doc.file_name);
        const props: Array<Record<string, unknown>> =
          (doc.extracted_data?.properties as Array<Record<string, unknown>>) ?? [];

        return (
          <div
            key={doc.id ?? doc.file_name}
            className="bg-white border border-amber-200 rounded-xl overflow-hidden"
          >
            {/* Header row */}
            <div className="flex items-center justify-between px-4 py-3 gap-3">
              <div className="flex items-center gap-2 min-w-0">
                <span className="inline-block w-2 h-2 rounded-full bg-amber-400 shrink-0" />
                <span className="text-sm font-medium text-gray-800 truncate">{doc.file_name}</span>
                <span className="text-xs text-gray-400 shrink-0">
                  {DOC_TYPE_LABELS[doc.document_type] ?? doc.document_type}
                </span>
                {doc.extraction_path && (
                  <span className="text-xs bg-amber-50 text-amber-700 border border-amber-200 rounded px-1.5 py-0.5 shrink-0">
                    {PATH_LABELS[doc.extraction_path] ?? doc.extraction_path}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-xs text-gray-400">{fmtDate(doc.processed_at)}</span>
                <button
                  onClick={() => isOpen ? closeReview() : openReview(doc)}
                  className="text-xs text-blue-600 hover:underline"
                >
                  {isOpen ? "Close" : "Review"}
                </button>
              </div>
            </div>

            {/* Extracted properties summary (collapsed) */}
            {!isOpen && props.length > 0 && (
              <div className="px-4 pb-3 border-t border-gray-50 pt-2 space-y-1">
                {props.slice(0, 3).map((p, i) => {
                  const label = (p.building_name as string | null) || (p.address as string | null) || `Property ${i + 1}`;
                  const sellPrice = p.sell_price != null ? Number(p.sell_price) : null;
                  const returnRate = p.return_rate != null ? Number(p.return_rate) : null;
                  return (
                    <p key={i} className="text-xs text-gray-600">
                      <span className="font-medium">{label}</span>
                      {sellPrice != null && <span className="text-gray-400"> · HKD {sellPrice.toLocaleString()}</span>}
                      {returnRate != null && <span className="text-gray-400"> · {(returnRate * 100).toFixed(1)}%</span>}
                    </p>
                  );
                })}
                {props.length > 3 && (
                  <p className="text-xs text-gray-400">+{props.length - 3} more properties</p>
                )}
              </div>
            )}

            {/* Edit pane (expanded) */}
            {isOpen && (
              <div className="border-t border-amber-100 px-4 pb-4 pt-3 space-y-3">
                <p className="text-xs text-gray-500">
                  Edit the JSON below to correct any extraction errors, then click Approve.
                </p>
                <textarea
                  value={editJson}
                  onChange={(e) => setEditJson(e.target.value)}
                  rows={20}
                  className="w-full font-mono text-xs border border-gray-200 rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y bg-gray-50"
                />
                {saveError && (
                  <p className="text-xs text-red-600">{saveError}</p>
                )}
                <div className="flex gap-2">
                  <button
                    onClick={() => handleApprove(doc)}
                    disabled={saving}
                    className="px-4 py-2 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
                  >
                    {saving ? "Saving…" : "Approve & Save"}
                  </button>
                  <button
                    onClick={closeReview}
                    className="px-4 py-2 border border-gray-200 text-sm rounded-lg hover:bg-gray-50 transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function VectorPage() {
  const [tab, setTab] = useState<"all" | "review">("all");
  const [reviewCount, setReviewCount] = useState<number | null>(null);

  useEffect(() => {
    getAdminDocuments(1000, true)
      .then((data) => setReviewCount(data.files.length))
      .catch(() => setReviewCount(null));
  }, []);

  return (
    <div className="flex flex-col h-full bg-gray-50">
      <header className="px-6 py-3 bg-white border-b border-gray-200 shrink-0">
        <p className="text-sm font-medium text-gray-700">Vector DB</p>
        <p className="text-xs text-gray-400">Azure AI Search — indexed documents</p>
      </header>

      {/* Tab bar */}
      <div className="flex gap-1 px-6 pt-3 pb-0 bg-white border-b border-gray-200 shrink-0">
        <button
          onClick={() => setTab("all")}
          className={`px-4 py-2 text-sm rounded-t-lg border-b-2 transition-colors ${
            tab === "all"
              ? "border-blue-500 text-blue-600 font-medium"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
        >
          All Documents
        </button>
        <button
          onClick={() => setTab("review")}
          className={`px-4 py-2 text-sm rounded-t-lg border-b-2 transition-colors flex items-center gap-1.5 ${
            tab === "review"
              ? "border-amber-500 text-amber-700 font-medium"
              : "border-transparent text-gray-500 hover:text-gray-700"
          }`}
        >
          Review Queue
          {reviewCount !== null && reviewCount > 0 && (
            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-amber-100 text-amber-700 text-xs font-semibold">
              {reviewCount}
            </span>
          )}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {tab === "all" ? <AllDocumentsTab /> : <ReviewQueueTab />}
      </div>
    </div>
  );
}
