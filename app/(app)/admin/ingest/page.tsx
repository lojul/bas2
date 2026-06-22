"use client";

import { useEffect, useRef, useState } from "react";
import {
  checkFile, checkOneDrive, listOneDriveFolders, processIngest, streamIngest, triageFile, updateDocument, uploadFiles,
} from "@/lib/api";
import type { CheckResult, IngestResult, OneDriveCheckResult, TriageResult } from "@/lib/api";

const TYPE_LABELS: Record<string, string> = {
  listing: "Single Listing",
  listing_list: "Multi Listing",
  pitching_deck: "Pitching Deck",
  news: "News",
  contact: "Name Card",
  unknown: "Unknown",
};

const TYPE_COLORS: Record<string, string> = {
  listing: "bg-blue-50 text-blue-700",
  listing_list: "bg-blue-50 text-blue-700",
  pitching_deck: "bg-purple-50 text-purple-700",
  news: "bg-yellow-50 text-yellow-700",
  contact: "bg-green-50 text-green-700",
  unknown: "bg-gray-100 text-gray-500",
};

const TYPE_FIELDS: Record<string, string> = {
  listing: "building name, address, district, size, rent, floor/unit, contact",
  listing_list: "building name, address, district, contact · unit table (size, floor, rent per unit)",
  pitching_deck: "project name, developer, address, available units, location, key features, design team, contact",
  news: "title, date, source, summary, topics",
  contact: "name, company, phone, email",
  unknown: "available fields",
};

const FIELD_LABELS: Record<string, string> = {
  building_name: "Building Name", address: "Address", district: "District",
  size_sqft: "Size (sqft)", rent_monthly: "Rent (HK$/mo)", floor_unit: "Floor / Unit",
  contact: "Contact", name: "Name", company: "Company", phone: "Phone", email: "Email",
  title: "Title", date: "Date", source: "Source", summary: "Summary", topics: "Topics",
  project_name: "Project Name", developer: "Developer", property_type: "Property Type",
  project_summary: "Project Summary", available_units: "Available Units",
  location: "Location", key_features: "Key Features", design_team: "Design Team",
  units: "Units", total_gfa: "Total GFA", floors: "Floors",
  leasing_agent: "Leasing Agent", website: "Website",
};

// ── Field renderers ────────────────────────────────────────────────────────────

const UNIT_KEY_ORDER = ["floor_unit", "size_sqft", "rent_monthly", "unit_type", "facing", "features", "notes"];

function ObjectArrayField({ items }: { items: Record<string, unknown>[] }) {
  const allKeys = Array.from(
    new Set(items.flatMap((item) => Object.keys(item).filter((k) => item[k] !== null && item[k] !== undefined && item[k] !== "")))
  ).sort((a, b) => {
    const ai = UNIT_KEY_ORDER.indexOf(a);
    const bi = UNIT_KEY_ORDER.indexOf(b);
    if (ai !== -1 && bi !== -1) return ai - bi;
    if (ai !== -1) return -1;
    if (bi !== -1) return 1;
    return a.localeCompare(b);
  });

  return (
    <div className="mt-1 w-full">
      <div className="rounded-lg border border-gray-100 overflow-x-auto">
        <table className="text-xs w-full">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-100">
              <th className="text-left px-2 py-1 text-gray-400 font-medium w-5">#</th>
              {allKeys.map((k) => (
                <th key={k} className="text-left px-2 py-1 text-gray-400 font-medium whitespace-nowrap">
                  {FIELD_LABELS[k] ?? k}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => (
              <tr key={i} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50">
                <td className="px-2 py-1 text-gray-300">{i + 1}</td>
                {allKeys.map((k) => {
                  const v = item[k];
                  const str = v === null || v === undefined || v === "" ? "" : typeof v === "object" ? JSON.stringify(v) : String(v);
                  return (
                    <td key={k} className="px-2 py-1 text-gray-700 whitespace-nowrap max-w-[12rem] truncate" title={str}>
                      {str || <span className="text-gray-300">—</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FieldRow({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined || value === "") return null;

  let display: React.ReactNode;

  if (Array.isArray(value)) {
    if (value.length === 0) return null;
    if (typeof value[0] === "object" && value[0] !== null) {
      display = <ObjectArrayField items={value as Record<string, unknown>[]} />;
    } else {
      display = <span>{(value as unknown[]).map(String).join(", ")}</span>;
    }
  } else if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).filter(
      ([, v]) => v !== null && v !== undefined && v !== ""
    );
    if (entries.length === 0) return null;
    display = (
      <div className="mt-0.5 space-y-0.5">
        {entries.map(([k, v]) => (
          <div key={k} className="flex gap-2">
            <span className="text-gray-400 shrink-0" style={{ minWidth: "5rem" }}>
              {FIELD_LABELS[k] ?? k}
            </span>
            <span className="text-gray-700 break-words">
              {typeof v === "object" ? JSON.stringify(v) : String(v ?? "")}
            </span>
          </div>
        ))}
      </div>
    );
  } else {
    display = <span>{String(value)}</span>;
  }

  const isTable = Array.isArray(value) && value.length > 0 && typeof (value as unknown[])[0] === "object" && (value as unknown[])[0] !== null;

  if (isTable) {
    return (
      <div className="py-1">
        <span className="text-gray-400 text-xs">{FIELD_LABELS[label] ?? label}</span>
        {display}
      </div>
    );
  }

  return (
    <div className="flex gap-3 py-0.5">
      <span className="text-gray-400 shrink-0 text-xs" style={{ minWidth: "7rem" }}>
        {FIELD_LABELS[label] ?? label}
      </span>
      <span className="text-gray-800 text-xs break-words flex-1">{display}</span>
    </div>
  );
}

function ExtractedFields({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(
    ([, v]) => v !== null && v !== undefined && v !== "" && !(Array.isArray(v) && v.length === 0)
  );
  if (entries.length === 0) return <p className="text-xs text-gray-400 italic">No fields extracted</p>;
  return (
    <div className="space-y-0.5">
      {entries.map(([k, v]) => <FieldRow key={k} label={k} value={v} />)}
    </div>
  );
}

// ── Edit form ─────────────────────────────────────────────────────────────────

const NUMERIC_FIELDS = new Set(["size_sqft", "rent_monthly", "total_gfa", "floors"]);

function isObjArray(v: unknown): v is Record<string, unknown>[] {
  return Array.isArray(v) && v.length > 0 && typeof v[0] === "object" && v[0] !== null;
}

function EditForm({
  data, docId, onSave, onCancel,
}: {
  data: Record<string, unknown>;
  docId: string;
  onSave: (updated: Record<string, unknown>) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState<Record<string, unknown>>(() => JSON.parse(JSON.stringify(data)));
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function setField(key: string, value: unknown) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  function setUnitCell(key: string, row: number, col: string, val: string) {
    setDraft((prev) => {
      const rows = JSON.parse(JSON.stringify(prev[key] as Record<string, unknown>[]));
      rows[row] = { ...rows[row], [col]: val };
      return { ...prev, [key]: rows };
    });
  }

  function addUnitRow(key: string) {
    const rows = draft[key] as Record<string, unknown>[];
    const blank = Object.fromEntries(Object.keys(rows[0] ?? {}).map((k) => [k, ""]));
    setField(key, [...rows, blank]);
  }

  function removeUnitRow(key: string, idx: number) {
    const rows = (draft[key] as Record<string, unknown>[]).filter((_, i) => i !== idx);
    setField(key, rows);
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await updateDocument(docId, draft);
      setSaved(true);
      onSave(draft);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save — please try again");
    } finally {
      setSaving(false);
    }
  }

  const inputCls = "border border-gray-200 rounded-lg px-3 py-1.5 text-sm w-full focus:outline-none focus:ring-2 focus:ring-blue-400";

  return (
    <div className="space-y-3 text-sm">
      {Object.entries(draft).map(([key, value]) => {
        const label = FIELD_LABELS[key] ?? key;

        if (isObjArray(value)) {
          const rows = value as Record<string, unknown>[];
          const cols = Array.from(new Set(rows.flatMap(Object.keys))).sort((a, b) => {
            const ai = UNIT_KEY_ORDER.indexOf(a), bi = UNIT_KEY_ORDER.indexOf(b);
            if (ai !== -1 && bi !== -1) return ai - bi;
            return ai !== -1 ? -1 : bi !== -1 ? 1 : a.localeCompare(b);
          });
          return (
            <div key={key}>
              <p className="text-xs text-gray-500 mb-1.5 font-medium">{label}</p>
              <div className="border border-gray-200 rounded-lg overflow-x-auto">
                <table className="text-xs w-full">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-100">
                      <th className="px-2 py-1.5 text-gray-400 font-medium w-6 text-center">#</th>
                      {cols.map((c) => (
                        <th key={c} className="text-left px-2 py-1.5 text-gray-400 font-medium whitespace-nowrap">
                          {FIELD_LABELS[c] ?? c}
                        </th>
                      ))}
                      <th className="w-6" />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, ri) => (
                      <tr key={ri} className="border-b border-gray-50 last:border-0">
                        <td className="px-2 py-1 text-gray-300 text-center">{ri + 1}</td>
                        {cols.map((c) => (
                          <td key={c} className="px-1 py-1">
                            <input
                              value={row[c] != null ? String(row[c]) : ""}
                              onChange={(e) => setUnitCell(key, ri, c, e.target.value)}
                              className="border border-gray-200 rounded px-1.5 py-0.5 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400 min-w-[5rem] w-full"
                            />
                          </td>
                        ))}
                        <td className="px-2 py-1 text-center">
                          <button onClick={() => removeUnitRow(key, ri)} className="text-gray-300 hover:text-red-400 text-xs" title="Remove">✕</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <button onClick={() => addUnitRow(key)} className="mt-1 text-xs text-blue-500 hover:text-blue-700">
                + Add row
              </button>
            </div>
          );
        }

        if (typeof value === "object" && value !== null && !Array.isArray(value)) {
          const obj = value as Record<string, unknown>;
          return (
            <div key={key}>
              <p className="text-xs text-gray-500 mb-1.5 font-medium">{label}</p>
              <div className="pl-3 border-l-2 border-gray-100 space-y-2">
                {Object.entries(obj).map(([sk, sv]) => (
                  <div key={sk} className="flex flex-col gap-0.5">
                    <label className="text-xs text-gray-400">{FIELD_LABELS[sk] ?? sk}</label>
                    <input
                      value={sv != null ? String(sv) : ""}
                      onChange={(e) => setField(key, { ...obj, [sk]: e.target.value })}
                      className={inputCls}
                    />
                  </div>
                ))}
              </div>
            </div>
          );
        }

        if (Array.isArray(value)) {
          return (
            <div key={key} className="flex flex-col gap-0.5">
              <label className="text-xs text-gray-500 font-medium">{label}</label>
              <input
                value={(value as unknown[]).map(String).join(", ")}
                onChange={(e) => setField(key, e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
                className={inputCls}
                placeholder="Separate values with commas"
              />
            </div>
          );
        }

        const isNum = NUMERIC_FIELDS.has(key);
        return (
          <div key={key} className="flex flex-col gap-0.5">
            <label className="text-xs text-gray-500 font-medium">{label}</label>
            <input
              type={isNum ? "number" : "text"}
              value={value != null ? String(value) : ""}
              onChange={(e) =>
                setField(key, isNum ? (e.target.value === "" ? null : Number(e.target.value)) : e.target.value)
              }
              className={inputCls}
            />
          </div>
        );
      })}

      <div className="flex items-center gap-2 pt-2 border-t border-gray-100">
        <button
          onClick={handleSave}
          disabled={saving || saved}
          className="bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-xs font-medium px-4 py-2 rounded-lg transition-colors"
        >
          {saving ? "Saving…" : saved ? "✓ Saved" : "Save changes"}
        </button>
        <button
          onClick={onCancel}
          className="text-xs text-gray-500 hover:text-gray-700 px-3 py-2 rounded-lg hover:bg-gray-50"
        >
          Cancel
        </button>
        {error && <p className="text-xs text-red-500 flex-1">{error}</p>}
      </div>
    </div>
  );
}

// ── ResultCard ────────────────────────────────────────────────────────────────

function ResultCard({ r, uploadedFolder }: { r: IngestResult; uploadedFolder?: string }) {
  const [showRaw, setShowRaw] = useState(false);
  const [editing, setEditing] = useState(false);
  const [localData, setLocalData] = useState<Record<string, unknown>>(r.extracted_data ?? {});
  const ed = localData;
  const hasFields = Object.keys(ed).length > 0;

  return (
    <div className="mt-2 bg-white border border-gray-200 rounded-xl overflow-hidden text-sm">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 flex-wrap">
        {r.status === "success" ? (
          <span className="text-green-600 font-medium text-base leading-none">✓</span>
        ) : (
          <span className="text-red-500 font-medium text-base leading-none">✗</span>
        )}
        <span className="font-medium text-gray-800 truncate">{r.file_name}</span>
        <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${TYPE_COLORS[r.document_type] ?? "bg-gray-100 text-gray-500"}`}>
          {TYPE_LABELS[r.document_type] ?? r.document_type}
        </span>
        {r.confidence > 0 && (
          <span className="text-xs text-gray-400">{Math.round(r.confidence * 100)}%</span>
        )}
        <span className="text-xs text-gray-400 ml-auto">
          {r.pages} page{r.pages !== 1 ? "s" : ""}
          {r.tables > 0 ? ` · ${r.tables} table${r.tables !== 1 ? "s" : ""}` : ""}
        </span>
      </div>

      {r.status === "error" ? (
        <div className="px-4 pb-3 border-t border-gray-50">
          <p className="mt-2 text-xs text-red-500">{r.error}</p>
        </div>
      ) : (
        <div className="border-t border-gray-100">
          {/* OneDrive section — only if uploaded */}
          {uploadedFolder && (
            <div className="px-4 py-2.5 border-b border-gray-50 bg-gray-50/50">
              <p className="text-xs font-medium text-gray-500 mb-1">OneDrive</p>
              <p className="text-xs text-gray-700 font-mono">
                {uploadedFolder}/{r.file_name}
              </p>
              <p className="text-xs text-gray-400 mt-0.5">
                Will be moved to /Processed when the timer runs (every 5 min)
              </p>
            </div>
          )}

          {/* Azure AI Search section */}
          <div className="px-4 py-2.5">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-1.5">
                <p className="text-xs font-medium text-gray-500">Azure AI Search</p>
                <span className="text-xs text-gray-300">·</span>
                <span className="text-xs text-gray-400 font-mono">processed-documents</span>
              </div>
              {hasFields && !editing && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => { setEditing(true); setShowRaw(false); }}
                    className="text-xs text-blue-500 hover:text-blue-700 font-medium"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => setShowRaw((v) => !v)}
                    className="text-xs text-gray-400 hover:text-gray-600"
                  >
                    {showRaw ? "Fields" : "Raw JSON"}
                  </button>
                </div>
              )}
            </div>

            {editing && r.index_id ? (
              <EditForm
                data={ed}
                docId={r.index_id}
                onSave={(updated) => { setLocalData(updated); setEditing(false); }}
                onCancel={() => setEditing(false)}
              />
            ) : hasFields ? (
              showRaw ? (
                <pre className="text-xs text-gray-600 bg-gray-50 rounded-lg p-3 overflow-x-auto max-h-56 whitespace-pre-wrap break-words">
                  {JSON.stringify(ed, null, 2)}
                </pre>
              ) : (
                <ExtractedFields data={ed} />
              )
            ) : (
              <p className="text-xs text-gray-400 italic">No structured fields extracted</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Message types ─────────────────────────────────────────────────────────────

type ConfirmInfo = {
  file: File;
  triage?: TriageResult;
  existing?: CheckResult;
  oneDrive?: OneDriveCheckResult;
  primaryLabel: string;
  secondaryLabel?: string;
  offerOneDriveSave: boolean; // show OneDrive save prompt after processing
};

type BotMsg = { role: "bot"; text: string; sub?: string; confirm?: ConfirmInfo };
type UserMsg = { role: "user"; text: string; fileName?: string };
type ResultsMsg = { role: "results"; results: IngestResult[]; uploadedFolder?: string };
type ResultItemMsg = { role: "result-item"; result: IngestResult; uploadedFolder?: string };
type SaveMsg = { role: "save"; file: File };
type Message = BotMsg | UserMsg | ResultsMsg | ResultItemMsg | SaveMsg;

const GREETING: Message = {
  role: "bot",
  text: "Please upload a PDF (or Word / PowerPoint / image) file and I'll process it for you.",
};

function isUrl(s: string) {
  return /^https?:\/\//i.test(s.trim());
}

function formatDate(iso?: string): string {
  if (!iso) return "previously";
  try {
    return new Date(iso).toLocaleDateString("en-HK", { day: "numeric", month: "short", year: "numeric" });
  } catch {
    return "previously";
  }
}

function extractHighlights(data?: Record<string, unknown>): string[] {
  if (!data) return [];
  const h: string[] = [];
  if (data.building_name) h.push(String(data.building_name));
  if (data.address) h.push(String(data.address));
  if (data.district) h.push(String(data.district));
  if (data.project_name) h.push(String(data.project_name));
  return h;
}

// ── Folder browser ────────────────────────────────────────────────────────────

function FolderBrowser({ selected, onSelect }: { selected: string; onSelect: (path: string) => void }) {
  const [browsePath, setBrowsePath] = useState(() => {
    // Start at parent of current selection so user can see it as a clickable item
    const p = selected.trim();
    if (!p || p === "/") return "/";
    const parts = p.split("/").filter(Boolean);
    return parts.length > 1 ? "/" + parts.slice(0, -1).join("/") : "/";
  });
  const [folders, setFolders] = useState<Array<{ name: string; path: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    listOneDriveFolders(browsePath)
      .then((data) => { if (!cancelled) { setFolders(data.folders); setLoading(false); } })
      .catch(() => { if (!cancelled) { setError("Could not load folders"); setLoading(false); } });
    return () => { cancelled = true; };
  }, [browsePath]);

  function navigate(path: string) {
    setBrowsePath(path);
    onSelect(path);
  }

  const parts = browsePath === "/" ? [] : browsePath.split("/").filter(Boolean);

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden text-xs">
      {/* Breadcrumb */}
      <div className="flex items-center gap-1 px-3 py-1.5 bg-gray-50 border-b border-gray-100 flex-wrap">
        <button onClick={() => navigate("/")} className="text-blue-600 hover:underline">OneDrive</button>
        {parts.map((part, i) => {
          const path = "/" + parts.slice(0, i + 1).join("/");
          return (
            <span key={i} className="flex items-center gap-1">
              <span className="text-gray-300">/</span>
              <button onClick={() => navigate(path)} className="text-blue-600 hover:underline">{part}</button>
            </span>
          );
        })}
      </div>

      {/* Folder list */}
      <div className="max-h-36 overflow-y-auto bg-white divide-y divide-gray-50">
        {/* "Use this folder" row for current level */}
        <button
          onClick={() => onSelect(browsePath === "/" ? "/" : browsePath)}
          className={`w-full text-left flex items-center gap-2 px-3 py-1.5 hover:bg-blue-50 ${
            selected === browsePath ? "bg-blue-50 text-blue-700 font-medium" : "text-gray-500"
          }`}
        >
          <span>·</span>
          <span className="italic">Use this folder ({browsePath === "/" ? "root" : browsePath.split("/").pop()})</span>
        </button>

        {loading && <p className="px-3 py-2 text-gray-400">Loading…</p>}
        {!loading && error && <p className="px-3 py-2 text-red-500">{error}</p>}
        {!loading && !error && folders.length === 0 && (
          <p className="px-3 py-2 text-gray-400 italic">No subfolders here</p>
        )}
        {folders.map((f) => (
          <button
            key={f.path}
            onClick={() => navigate(f.path)}
            className={`w-full text-left flex items-center gap-2 px-3 py-1.5 hover:bg-blue-50 ${
              selected === f.path ? "bg-blue-50 text-blue-700 font-medium" : "text-gray-700"
            }`}
          >
            <span className="text-gray-400">📁</span>
            {f.name}
            <span className="ml-auto text-gray-300">›</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Confirm block ─────────────────────────────────────────────────────────────

function ConfirmBlock({
  info,
  busy,
  onPrimary,
  onSecondary,
  onCancel,
}: {
  info: ConfirmInfo;
  busy: boolean;
  onPrimary: (info: ConfirmInfo) => void;
  onSecondary: (info: ConfirmInfo) => void;
  onCancel: () => void;
}) {
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      <button
        onClick={() => onPrimary(info)}
        disabled={busy}
        className="px-3 py-1.5 text-xs font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-40 transition-colors"
      >
        {info.primaryLabel}
      </button>
      {info.secondaryLabel && (
        <button
          onClick={() => onSecondary(info)}
          disabled={busy}
          className="px-3 py-1.5 text-xs font-medium bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 disabled:opacity-40 transition-colors"
        >
          {info.secondaryLabel}
        </button>
      )}
      <button
        onClick={onCancel}
        disabled={busy}
        className="px-3 py-1.5 text-xs font-medium bg-gray-100 text-gray-500 rounded-lg hover:bg-gray-200 disabled:opacity-40 transition-colors"
      >
        Cancel
      </button>
    </div>
  );
}

// ── Save to OneDrive block ────────────────────────────────────────────────────

function SaveBlock({
  file,
  defaultFolder,
  busy,
  onSave,
  onSkip,
}: {
  file: File;
  defaultFolder: string;
  busy: boolean;
  onSave: (file: File, folder: string) => void;
  onSkip: () => void;
}) {
  const [folder, setFolder] = useState(defaultFolder);
  const [showBrowser, setShowBrowser] = useState(false);

  return (
    <div className="flex justify-start">
      <div className="max-w-sm bg-white border border-gray-200 text-gray-700 text-sm px-4 py-3 rounded-2xl rounded-bl-sm space-y-2">
        <p>Save <span className="font-medium">{file.name}</span> to OneDrive?</p>
        <div className="space-y-1.5">
          <div className="flex gap-1.5">
            <input
              type="text"
              value={folder}
              onChange={(e) => { setFolder(e.target.value); setShowBrowser(false); }}
              placeholder="/Document Processor/In"
              className="flex-1 text-xs font-mono border border-gray-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-300 bg-white text-gray-800"
            />
            <button
              onClick={() => setShowBrowser((v) => !v)}
              className={`shrink-0 text-xs px-2.5 py-1.5 border rounded-lg transition-colors ${
                showBrowser
                  ? "bg-blue-50 border-blue-300 text-blue-700"
                  : "border-gray-200 text-gray-500 hover:bg-gray-50"
              }`}
            >
              Browse
            </button>
          </div>
          {showBrowser && (
            <FolderBrowser selected={folder} onSelect={(path) => setFolder(path)} />
          )}
          <p className="text-xs text-gray-400">New folders will be created automatically.</p>
        </div>
        <div className="flex gap-2 pt-1">
          <button
            onClick={() => onSave(file, folder)}
            disabled={busy || !folder.trim()}
            className="px-3 py-1.5 text-xs font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-40 transition-colors"
          >
            Save to OneDrive
          </button>
          <button
            onClick={onSkip}
            disabled={busy}
            className="px-3 py-1.5 text-xs font-medium bg-gray-100 text-gray-500 rounded-lg hover:bg-gray-200 disabled:opacity-40 transition-colors"
          >
            Skip
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function IngestPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<(() => void) | null>(null);
  const [messages, setMessages] = useState<Message[]>([GREETING]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  function push(msg: Message) {
    setMessages((prev) => [...prev, msg]);
  }

  function updateLastBot(patch: Partial<BotMsg>) {
    setMessages((prev) => {
      const next = [...prev];
      for (let i = next.length - 1; i >= 0; i--) {
        if (next[i].role === "bot") {
          next[i] = { ...next[i] as BotMsg, ...patch };
          return next;
        }
      }
      return next;
    });
  }

  // ── Process file ───────────────────────────────────────────────────────────

  async function runProcess(file: File, offerOneDriveSave = false) {
    setBusy(true);
    push({ role: "bot", text: `Processing ${file.name}…` });
    try {
      const data = await processIngest(file);
      if (!data.results.length) {
        updateLastBot({ text: "No supported files found." });
      } else {
        const ok = data.results.filter((r) => r.status === "success").length;
        const total = data.results.length;
        updateLastBot({
          text: ok === total
            ? `Done — ${total} file${total !== 1 ? "s" : ""} indexed.`
            : `Done — ${ok}/${total} succeeded.`,
        });
        push({ role: "results", results: data.results });
        if (offerOneDriveSave && ok > 0) {
          push({ role: "save", file });
        }
      }
    } catch (e: unknown) {
      updateLastBot({ text: `Error: ${e instanceof Error ? e.message : "Processing failed"}` });
    } finally {
      setBusy(false);
    }
  }

  // ── OneDrive save (post-processing) ────────────────────────────────────────

  async function handleSave(file: File, folder: string) {
    setMessages((prev) => prev.filter((m) => m.role !== "save"));
    setBusy(true);
    push({ role: "bot", text: `Saving ${file.name} to ${folder}…` });
    try {
      const result = await uploadFiles([file], folder);
      const uploaded = result.results[0];
      updateLastBot({
        text: uploaded?.ok
          ? `Saved to ${result.folder}/${file.name}`
          : `Save failed: ${uploaded?.error ?? "Unknown error"}`,
      });
    } catch (e: unknown) {
      updateLastBot({ text: `Save error: ${e instanceof Error ? e.message : "Unknown"}` });
    } finally {
      setBusy(false);
    }
  }

  function handleSkip() {
    setMessages((prev) => prev.filter((m) => m.role !== "save"));
  }

  // ── Interactive pre-check ───────────────────────────────────────────────────

  async function prepareFile(file: File) {
    setBusy(true);
    push({ role: "bot", text: "Checking if already indexed…" });

    try {
      // Step 1: Azure Search — already indexed?
      const check = await checkFile(file.name);
      if (check.exists) {
        const typeLabel = TYPE_LABELS[check.document_type ?? "unknown"] ?? check.document_type ?? "Unknown";
        const highlights = extractHighlights(check.extracted_data);
        const subParts = [...highlights, "Stored in Azure AI Search (processed-documents)"];
        updateLastBot({
          text: `Previously processed on ${formatDate(check.processed_at)} as ${typeLabel}. Process again?`,
          sub: subParts.join(" · "),
          confirm: {
            file,
            existing: check,
            primaryLabel: "Process again",
            offerOneDriveSave: false,
          },
        });
        setBusy(false);
        return;
      }

      // Step 2: OneDrive — where is the file?
      updateLastBot({ text: "Not in the index. Checking OneDrive…" });
      const od = await checkOneDrive(file.name);

      if (od.drive_configured) {
        if (od.in_inbox) {
          updateLastBot({
            text: `Found in OneDrive at ${od.inbox_folder}/${file.name}`,
            sub: "Already queued — auto-processes every 5 min. Process it now instead?",
            confirm: {
              file,
              oneDrive: od,
              primaryLabel: "Process now",
              offerOneDriveSave: false,
            },
          });
          setBusy(false);
          return;
        }

        if (od.in_processed) {
          updateLastBot({
            text: `Found in OneDrive at ${od.processed_folder}/${file.name} — previously processed via the timer pipeline.`,
            sub: "Process again?",
            confirm: {
              file,
              oneDrive: od,
              primaryLabel: "Process again",
              offerOneDriveSave: false,
            },
          });
          setBusy(false);
          return;
        }
      }

      // Step 3: File not found anywhere — run triage
      updateLastBot({ text: "Not found in OneDrive. Analysing the file…" });
      const triage = await triageFile(file);

      if (!triage.can_process) {
        updateLastBot({
          text: `Cannot process this file: ${triage.reason ?? `${triage.format} files are not supported`}.`,
        });
        setBusy(false);
        return;
      }

      const typeLabel = TYPE_LABELS[triage.detected_type] ?? triage.detected_type ?? "Unknown";
      const pct = triage.confidence > 0 ? ` (${Math.round(triage.confidence * 100)}% confidence)` : "";
      const fields = TYPE_FIELDS[triage.detected_type] ?? TYPE_FIELDS.unknown;
      updateLastBot({
        text: `Looks like a ${typeLabel}${pct}. Ready to process?`,
        sub: `Will extract: ${fields} → saved to Azure AI Search (processed-documents)`,
        confirm: {
          file,
          triage,
          oneDrive: od,
          primaryLabel: "Process it",
          offerOneDriveSave: od.drive_configured,
        },
      });
    } catch (e: unknown) {
      updateLastBot({ text: `Error: ${e instanceof Error ? e.message : "Check failed"}` });
    }

    setBusy(false);
  }

  function handlePrimary(info: ConfirmInfo) {
    updateLastBot({ confirm: undefined });
    runProcess(info.file, info.offerOneDriveSave);
  }

  function handleSecondary(info: ConfirmInfo) {
    updateLastBot({ confirm: undefined });
    runProcess(info.file, false);
  }

  function handleCancel() {
    updateLastBot({ text: "Cancelled.", confirm: undefined, sub: undefined });
  }

  // ── Folder stream flow (unchanged) ─────────────────────────────────────────

  function runFolder(folderPath: string) {
    setBusy(true);
    push({ role: "bot", text: `Scanning ${folderPath}…` });
    // Derive processed folder: /Document Processor/In → /Document Processor/Processed
    const processedFolder = folderPath.replace(/\/In\s*$/, "/Processed");

    cancelRef.current = streamIngest(
      folderPath,
      (count, files) => {
        updateLastBot({ text: `Found ${count} file${count !== 1 ? "s" : ""}`, sub: files.join(", ") });
      },
      (result) => {
        push({ role: "result-item", result, uploadedFolder: processedFolder });
      },
      (ok, total, message) => {
        if (message) {
          push({ role: "bot", text: message });
        } else {
          push({
            role: "bot",
            text: ok === total
              ? `Done — ${total} file${total !== 1 ? "s" : ""} indexed.`
              : `Done — ${ok}/${total} succeeded.`,
          });
        }
        setBusy(false);
        cancelRef.current = null;
      },
      (err) => {
        push({ role: "bot", text: `Error: ${err}` });
        setBusy(false);
        cancelRef.current = null;
      },
    );
  }

  // ── Input handlers ──────────────────────────────────────────────────────────

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    push({ role: "user", text: file.name, fileName: file.name });
    if (fileInputRef.current) fileInputRef.current.value = "";
    prepareFile(file);
  }

  function handleSend() {
    const path = input.trim();
    if (!path || busy) return;
    setInput("");
    push({ role: "user", text: path });
    if (isUrl(path)) {
      push({
        role: "bot",
        text: "That looks like a URL — please enter a folder path instead.",
        sub: "Example: /Document Processor/In",
      });
      return;
    }
    runFolder(path);
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full bg-gray-50">
      <header className="px-6 py-3 bg-white border-b border-gray-200 shrink-0">
        <p className="text-sm font-medium text-gray-700">Ingest</p>
        <p className="text-xs text-gray-400">Upload a file or enter a OneDrive folder path</p>
      </header>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
        {messages.map((msg, i) => {
          if (msg.role === "save") {
            return (
              <SaveBlock
                key={i}
                file={msg.file}
                defaultFolder={"/Document Processor/In"}
                busy={busy}
                onSave={handleSave}
                onSkip={handleSkip}
              />
            );
          }
          if (msg.role === "results") {
            return (
              <div key={i} className="space-y-2">
                {msg.results.map((r, j) => (
                  <ResultCard key={j} r={r} uploadedFolder={msg.uploadedFolder} />
                ))}
              </div>
            );
          }
          if (msg.role === "result-item") return (
            <ResultCard key={i} r={msg.result} uploadedFolder={msg.uploadedFolder} />
          );
          if (msg.role === "user") {
            return (
              <div key={i} className="flex justify-end">
                <div className="max-w-sm bg-blue-600 text-white text-sm px-4 py-2 rounded-2xl rounded-br-sm break-all">
                  {msg.fileName ? (
                    <span className="flex items-center gap-1.5">
                      <span className="text-blue-200 text-xs">📄</span>
                      {msg.text}
                    </span>
                  ) : msg.text}
                </div>
              </div>
            );
          }

          // bot
          const isLast = i === messages.length - 1;
          const hasConfirm = !!msg.confirm && isLast;
          return (
            <div key={i} className="flex justify-start">
              <div className="max-w-sm bg-white border border-gray-200 text-gray-700 text-sm px-4 py-2.5 rounded-2xl rounded-bl-sm">
                <span>{msg.text}</span>
                {busy && isLast && !hasConfirm && (
                  <span className="ml-1 inline-block w-1 h-3 bg-gray-400 animate-pulse rounded-sm align-middle" />
                )}
                {msg.sub && (
                  <p className="mt-0.5 text-xs text-gray-400">{msg.sub}</p>
                )}
                {hasConfirm && (
                  <ConfirmBlock
                    info={msg.confirm!}
                    busy={busy}
                    onPrimary={handlePrimary}
                    onSecondary={handleSecondary}
                    onCancel={handleCancel}
                  />
                )}

              </div>
            </div>
          );
        })}
      </div>

      {/* Input bar — file upload only */}
      <div className="shrink-0 bg-white border-t border-gray-200 px-4 py-4">
        <div className="flex items-center justify-center max-w-2xl mx-auto">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,.docx,.pptx"
            className="hidden"
            onChange={handleFileChange}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={busy}
            className="flex items-center gap-2.5 px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm font-medium rounded-2xl transition-colors shadow-sm"
          >
            <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
            </svg>
            Select a document to process
          </button>
        </div>
      </div>
    </div>
  );
}
