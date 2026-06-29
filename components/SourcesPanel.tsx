"use client";

import { useState } from "react";
import type { Source } from "@/lib/api";

const DOC_TYPE_LABELS: Record<string, string> = {
  listing:       "Single Listing",
  listing_list:  "Multi Listing",
  pitching_deck: "Pitching Deck",
  news:          "News",
  contact:       "Contact",
};

function docTypeLabel(type?: string) {
  return type ? (DOC_TYPE_LABELS[type] ?? type) : "";
}

function str(v: unknown): string | null {
  return v != null && v !== "" ? String(v) : null;
}

interface Unit {
  floor?: string;
  unit?: string;
  size?: number;
  rent?: number;
}

function FieldRow({ label, value }: { label: string; value: unknown }) {
  const s = str(value);
  if (!s) return null;
  return (
    <div className="flex gap-2 py-0.5">
      <span className="w-28 shrink-0 text-gray-400">{label}</span>
      <span className="font-medium text-gray-800 break-words">{s}</span>
    </div>
  );
}

function UnitsTable({ units }: { units: Unit[] }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? units : units.slice(0, 3);

  return (
    <div>
      <table className="w-full text-xs mt-1">
        <thead>
          <tr className="border-b border-gray-100 text-gray-400">
            <th className="text-left font-normal py-1 pr-3">Floor / Unit</th>
            <th className="text-right font-normal py-1 pr-3">Size (sqft)</th>
            <th className="text-right font-normal py-1">Rent (HK$/mo)</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((u, i) => (
            <tr key={i} className="border-b border-gray-50">
              <td className="py-1 pr-3 text-gray-700">
                {[u.floor, u.unit].filter(Boolean).join(" ") || "—"}
              </td>
              <td className="py-1 pr-3 text-right text-gray-700">
                {u.size != null ? u.size.toLocaleString() : "—"}
              </td>
              <td className="py-1 text-right text-gray-700">
                {u.rent != null ? `$${u.rent.toLocaleString()}` : "On request"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {units.length > 3 && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-1 text-xs text-blue-600 hover:underline"
        >
          {expanded ? "▴ Show less" : `▾ Show all ${units.length} units`}
        </button>
      )}
    </div>
  );
}

function ExtractedData({
  dtype,
  data,
}: {
  dtype: string;
  data: Record<string, unknown>;
}) {
  if (dtype === "listing") {
    return (
      <div className="text-xs mt-2 space-y-0.5">
        <FieldRow label="Building Name" value={data.building_name} />
        <FieldRow label="Address"       value={data.address} />
        <FieldRow label="District"      value={data.district} />
        <FieldRow label="Floor / Unit"  value={data.floor_unit} />
        <FieldRow
          label="Size"
          value={data.size_sqft ? `${data.size_sqft} sqft` : null}
        />
        <FieldRow
          label="Rent (mo)"
          value={
            data.rent_monthly
              ? `HK$${Number(data.rent_monthly).toLocaleString()}/mo`
              : data.rent_monthly === 0
              ? "By offer"
              : null
          }
        />
        <FieldRow label="Contact"       value={data.contact_phone ?? data.contact} />
      </div>
    );
  }

  if (dtype === "listing_list") {
    const units = Array.isArray(data.units) ? (data.units as Unit[]) : [];
    return (
      <div className="text-xs mt-2 space-y-0.5">
        <FieldRow label="Building Name"  value={data.building_name} />
        <FieldRow label="Address"        value={data.address} />
        <FieldRow label="District"       value={data.district} />
        <FieldRow
          label="Asking Price (HK$)"
          value={data.asking_price != null ? Number(data.asking_price).toLocaleString() : null}
        />
        <FieldRow
          label="Rental Income (mo)"
          value={data.rental_income != null ? `HK$${Number(data.rental_income).toLocaleString()}` : null}
        />
        <FieldRow label="Contact"        value={data.contact_phone ?? data.contact} />
        {units.length > 0 ? (
          <div className="pt-1">
            <span className="text-gray-400">Units</span>
            <span className="ml-2 text-gray-500">({units.length} available)</span>
            <UnitsTable units={units} />
          </div>
        ) : null}
      </div>
    );
  }

  if (dtype === "news") {
    return (
      <div className="text-xs mt-2 space-y-0.5">
        <FieldRow label="Title"   value={data.title_zh ?? data.title} />
        <FieldRow label="Source"  value={data.source} />
        <FieldRow label="Date"    value={data.date} />
        {data.summary ? (
          <p className="text-gray-500 mt-1 leading-relaxed line-clamp-3">
            {String(data.summary)}
          </p>
        ) : null}
      </div>
    );
  }

  if (dtype === "contact") {
    return (
      <div className="text-xs mt-2 space-y-0.5">
        <FieldRow label="Name"    value={data.name} />
        <FieldRow label="Company" value={data.company} />
        <FieldRow label="Phone"   value={data.phone} />
        <FieldRow label="Email"   value={data.email} />
      </div>
    );
  }

  return null;
}

export function SourcesPanel({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState(false);
  if (!sources.length) return null;

  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-xs text-blue-600 hover:underline"
      >
        {open ? "▾" : "▸"} Sources ({sources.length})
      </button>

      {open && (
        <ul className="mt-2 space-y-2">
          {sources.map((s, i) => {
            const extracted = (s.extracted_data ?? {}) as Record<string, unknown>;
            const dtype = s.document_type ?? "";
            const scorePercent = s.score != null ? `${Math.round(s.score * 100)}%` : null;

            return (
              <li key={i} className="bg-gray-50 border border-gray-100 rounded-lg p-3 text-xs">
                {/* Header */}
                <div className="flex items-start gap-2 flex-wrap">
                  <span className="text-green-600 font-bold shrink-0">✓</span>
                  <span className="font-medium text-gray-800 flex-1 min-w-0 break-words">
                    {s.file_name}
                  </span>
                  {dtype && (
                    <span className="shrink-0 bg-blue-100 text-blue-700 rounded px-1.5 py-0.5">
                      {docTypeLabel(dtype)}
                    </span>
                  )}
                  {scorePercent && (
                    <span className="shrink-0 text-gray-400">{scorePercent}</span>
                  )}
                </div>

                {/* Index breadcrumb */}
                {s.index && (
                  <p className="mt-1 text-gray-400">
                    Azure AI Search · <span className="font-mono">{s.index}</span>
                  </p>
                )}

                {/* Structured extracted data */}
                {Object.keys(extracted).length > 0 && dtype && (
                  <ExtractedData dtype={dtype} data={extracted} />
                )}

                {/* Images */}
                {s.image_urls && s.image_urls.length > 0 && (
                  <div className="mt-2 flex gap-2 flex-wrap">
                    {s.image_urls.slice(0, 3).map((url, j) => (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        key={j}
                        src={url}
                        alt={`${s.file_name} image ${j + 1}`}
                        className="h-16 w-auto rounded border border-gray-200 object-cover"
                      />
                    ))}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
