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

interface Unit { floor?: string; unit?: string; size?: number; rent?: number; }

function UnitsTable({ units }: { units: Unit[] }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? units : units.slice(0, 4);
  return (
    <div>
      <table className="w-full text-xs mt-1 border-t border-gray-100">
        <thead>
          <tr className="text-gray-400">
            <th className="text-left font-normal py-1 pr-3">Floor / Unit</th>
            <th className="text-right font-normal py-1 pr-3">Size (sqft)</th>
            <th className="text-right font-normal py-1">Rent (HK$/mo)</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((u, i) => (
            <tr key={i} className="border-t border-gray-50">
              <td className="py-1 pr-3">{[u.floor, u.unit].filter(Boolean).join(" ") || "—"}</td>
              <td className="py-1 pr-3 text-right">{u.size != null ? u.size.toLocaleString() : "—"}</td>
              <td className="py-1 text-right">{u.rent != null ? `$${u.rent.toLocaleString()}` : "On request"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {units.length > 4 && (
        <button onClick={() => setExpanded(!expanded)} className="mt-1 text-xs text-blue-600 hover:underline">
          {expanded ? "▴ Show less" : `▾ Show all ${units.length} units`}
        </button>
      )}
    </div>
  );
}

function ResultCard({ doc }: { doc: Source & Record<string, unknown> }) {
  const extracted = (doc.extracted_data ?? {}) as Record<string, unknown>;
  const dtype = doc.document_type ?? "unknown";
  const indexName = str((doc as Record<string, unknown>).index);
  const scorePercent = doc.score != null ? `${Math.round((doc.score as number) * 100)}%` : null;

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-2">
      {/* Header */}
      <div className="flex items-start gap-2 flex-wrap">
        <span className="text-green-600 font-bold">✓</span>
        <span className="font-medium text-gray-900 text-sm flex-1">{doc.file_name}</span>
        {dtype && dtype !== "unknown" ? (
          <span className="bg-blue-100 text-blue-700 text-xs rounded px-1.5 py-0.5">{docTypeLabel(dtype)}</span>
        ) : null}
        {scorePercent && <span className="text-gray-400 text-xs">{scorePercent}</span>}
      </div>

      {/* Index breadcrumb */}
      {indexName && (
        <p className="text-xs text-gray-400">Azure AI Search · <span className="font-mono">{indexName}</span></p>
      )}

      {/* Single listing */}
      {dtype === "listing" ? (
        <div className="grid grid-cols-2 gap-x-6 gap-y-0.5 text-xs text-gray-600 pt-1">
          <Field label="Building Name" value={extracted.building_name} />
          <Field label="Address" value={extracted.address} />
          <Field label="District" value={extracted.district} />
          <Field label="Floor / Unit" value={extracted.floor_unit} />
          <Field label="Size" value={extracted.size_sqft ? `${extracted.size_sqft} sqft` : null} />
          <Field label="Rent (mo)" value={extracted.rent_monthly ? `HK$${Number(extracted.rent_monthly).toLocaleString()}` : "By offer"} />
          <Field label="Contact" value={extracted.contact_phone ?? extracted.contact} />
        </div>
      ) : null}

      {/* Multi listing */}
      {dtype === "listing_list" ? (
        <div className="text-xs text-gray-600 space-y-0.5 pt-1">
          <FieldP label="Building Name" value={extracted.building_name} />
          <FieldP label="Address" value={extracted.address} />
          <FieldP label="District" value={extracted.district} />
          <FieldP
            label="Asking Price (HK$)"
            value={extracted.asking_price != null ? Number(extracted.asking_price).toLocaleString() : null}
          />
          <FieldP
            label="Monthly Rental Income (HK$)"
            value={extracted.rental_income != null ? Number(extracted.rental_income).toLocaleString() : null}
          />
          <FieldP label="Contact" value={extracted.contact_phone ?? extracted.contact} />
          {Array.isArray(extracted.units) && (extracted.units as Unit[]).length > 0 ? (
            <div className="pt-1">
              <p className="text-gray-500 font-medium">{(extracted.units as Unit[]).length} units available</p>
              <UnitsTable units={extracted.units as Unit[]} />
            </div>
          ) : null}
        </div>
      ) : null}

      {/* News */}
      {dtype === "news" ? (
        <div className="text-xs text-gray-600 space-y-0.5 pt-1">
          <FieldP value={extracted.title_zh ?? extracted.title} className="font-medium text-gray-800" />
          <FieldP label="Source" value={extracted.source} />
          <FieldP label="Date" value={extracted.date} />
          <FieldP value={extracted.summary} className="text-gray-500 line-clamp-3 mt-1" />
        </div>
      ) : null}

      {/* Contact */}
      {dtype === "contact" ? (
        <div className="text-xs text-gray-600 space-y-0.5 pt-1">
          <FieldP label="Name" value={extracted.name} />
          <FieldP label="Company" value={extracted.company} />
          <FieldP label="Phone" value={extracted.phone} />
          <FieldP label="Email" value={extracted.email} />
        </div>
      ) : null}

      {/* Images */}
      {Array.isArray(doc.image_urls) && doc.image_urls.length > 0 ? (
        <div className="flex gap-2 flex-wrap pt-1">
          {doc.image_urls.slice(0, 3).map((url, i) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img key={i} src={url} alt={`${doc.file_name} image ${i + 1}`}
              className="h-16 w-auto rounded border border-gray-200 object-cover" />
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
