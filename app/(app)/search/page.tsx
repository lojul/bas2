"use client";

import { useState } from "react";
import { search } from "@/lib/api";
import type { Source } from "@/lib/api";

const DOC_TYPE_LABELS: Record<string, string> = {
  listing: "Single Listing",
  listing_list: "Multi Listing",
  pitching_deck: "Pitching Deck",
  news: "News",
  contact: "Contact",
};

function docTypeLabel(type?: string) {
  return type ? (DOC_TYPE_LABELS[type] ?? type) : "";
}

function str(v: unknown): string | null {
  return v != null && v !== "" ? String(v) : null;
}

function Field({ label, value }: { label: string; value: unknown }) {
  const s = str(value);
  if (!s) return null;
  return <span><b>{label}:</b> {s}</span>;
}

function FieldP({ label, value, className }: { label?: string; value: unknown; className?: string }) {
  const s = str(value);
  if (!s) return null;
  return <p className={className}>{label ? <><b>{label}:</b> {s}</> : s}</p>;
}

function ResultCard({ doc }: { doc: Source & Record<string, unknown> }) {
  const extracted = (doc.extracted_data ?? {}) as Record<string, unknown>;
  const dtype = doc.document_type ?? "unknown";
  const indexName = str((doc as Record<string, unknown>).index);

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-2">
      <div className="flex items-start gap-2 flex-wrap">
        <span className="font-medium text-gray-900 text-sm">{doc.file_name}</span>
        {dtype ? (
          <span className="bg-blue-100 text-blue-700 text-xs rounded px-1.5 py-0.5">
            {docTypeLabel(dtype)}
          </span>
        ) : null}
        {indexName ? (
          <span className="bg-gray-100 text-gray-500 text-xs rounded px-1.5 py-0.5">
            {indexName}
          </span>
        ) : null}
      </div>

      {dtype === "listing" ? (
        <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs text-gray-600">
          <Field label="Building" value={extracted.building_name} />
          <Field label="Address" value={extracted.address} />
          <Field label="District" value={extracted.district} />
          <Field label="Unit" value={extracted.floor_unit} />
          <Field label="Size" value={extracted.size_sqft ? `${extracted.size_sqft} sqft` : null} />
          <Field label="Rent" value={extracted.rent_monthly ? `HK$${extracted.rent_monthly}/mo` : "By Offer"} />
        </div>
      ) : null}

      {dtype === "listing_list" ? (
        <div className="text-xs text-gray-600 space-y-0.5">
          <FieldP label="Building" value={extracted.building_name} />
          <FieldP label="Address" value={extracted.address} />
          {Array.isArray(extracted.units) ? (
            <p><b>Units:</b> {extracted.units.length} available</p>
          ) : null}
        </div>
      ) : null}

      {dtype === "news" ? (
        <div className="text-xs text-gray-600 space-y-0.5">
          <FieldP value={extracted.title} className="font-medium" />
          <FieldP label="Source" value={extracted.source} />
          <FieldP value={extracted.summary} className="text-gray-500 line-clamp-2" />
        </div>
      ) : null}

      {dtype === "contact" ? (
        <div className="text-xs text-gray-600 space-y-0.5">
          <FieldP label="Name" value={extracted.name} />
          <FieldP label="Company" value={extracted.company} />
          <FieldP label="Phone" value={extracted.phone} />
        </div>
      ) : null}

      {Array.isArray(doc.image_urls) && doc.image_urls.length > 0 ? (
        <div className="flex gap-2 flex-wrap pt-1">
          {doc.image_urls.slice(0, 3).map((url, i) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={i}
              src={url}
              alt={`${doc.file_name} image ${i + 1}`}
              className="h-16 w-auto rounded border border-gray-200 object-cover"
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Source[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState("");

  async function handleSearch() {
    const q = query.trim();
    setError("");
    setLoading(true);
    setSearched(true);
    try {
      const data = await search(q, 100);
      setResults(data.results ?? []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Search failed");
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") handleSearch();
  }

  return (
    <div className="flex flex-col h-full bg-gray-50">
      <header className="px-6 py-3 bg-white border-b border-gray-200 shrink-0">
        <div className="flex items-center gap-3">
          <p className="text-sm font-medium text-gray-700">Keyword Search</p>
          <span className="text-xs text-gray-400">Powered by Azure AI Search</span>
        </div>
        <p className="text-xs text-gray-400">Keyword search across all indexed documents</p>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-4">
        {/* Search input */}
        <div className="flex gap-3 max-w-2xl mb-4">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="e.g. 中環 / Central / building name / address"
            className="flex-1 border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            onClick={handleSearch}
            disabled={loading}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white rounded-xl px-5 py-2.5 text-sm font-medium transition-colors shrink-0"
          >
            {loading ? "…" : "Search"}
          </button>
        </div>

        {error && <p className="text-sm text-red-600 mb-3">{error}</p>}

        {/* Results */}
        {searched && !loading && (
          <p className="text-xs text-gray-500 mb-3">
            {results.length > 0 ? `${results.length} results` : "No results found"}
          </p>
        )}

        <div className="space-y-3 max-w-2xl">
          {results.map((doc, i) => (
            <ResultCard key={i} doc={doc as Source & Record<string, unknown>} />
          ))}
        </div>
      </div>
    </div>
  );
}
