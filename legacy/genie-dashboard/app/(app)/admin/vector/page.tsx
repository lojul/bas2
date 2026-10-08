"use client";

import { useEffect, useState } from "react";
import { getAdminDocuments } from "@/lib/api";
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

export default function VectorPage() {
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

  return (
    <div className="flex flex-col h-full bg-gray-50">
      <header className="px-6 py-3 bg-white border-b border-gray-200 shrink-0">
        <p className="text-sm font-medium text-gray-700">Vector DB</p>
        <p className="text-xs text-gray-400">Azure AI Search — indexed documents</p>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {loading && <p className="text-sm text-gray-500">Loading…</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}

        {!loading && !error && (
          <>
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
                      <span className="truncate text-gray-800">{doc.file_name}</span>
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
          </>
        )}
      </div>
    </div>
  );
}
