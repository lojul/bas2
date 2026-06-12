"use client";

import { useState } from "react";
import type { Source } from "@/lib/api";

function docTypeLabel(type?: string) {
  const map: Record<string, string> = {
    listing: "Single Listing",
    listing_list: "Multi Listing",
    pitching_deck: "Pitching Deck",
    news: "News",
    contact: "Contact",
  };
  return type ? (map[type] ?? type) : "";
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
          {sources.map((s, i) => (
            <li key={i} className="bg-gray-50 rounded-lg p-3 text-xs">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-gray-800">{s.file_name}</span>
                {s.document_type && (
                  <span className="bg-blue-100 text-blue-700 rounded px-1.5 py-0.5">
                    {docTypeLabel(s.document_type)}
                  </span>
                )}
                {s.index && (
                  <span className="bg-gray-200 text-gray-600 rounded px-1.5 py-0.5">
                    {s.index}
                  </span>
                )}
                {s.score !== undefined && (
                  <span className="text-gray-400">score {s.score.toFixed(2)}</span>
                )}
              </div>

              {/* Images (max 3) */}
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
          ))}
        </ul>
      )}
    </div>
  );
}
