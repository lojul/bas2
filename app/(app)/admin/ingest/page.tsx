"use client";

import { useEffect, useRef, useState } from "react";
import {
  checkFile, checkOneDrive, listOneDriveFolders, processIngest, streamIngest, triageFile, uploadFiles,
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

function FieldRow({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined || value === "") return null;

  let display: React.ReactNode;

  if (Array.isArray(value)) {
    if (value.length === 0) return null;
    if (typeof value[0] === "object" && value[0] !== null) {
      display = <span className="text-gray-400 italic">{value.length} item{value.length !== 1 ? "s" : ""}</span>;
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

// ── ResultCard ────────────────────────────────────────────────────────────────

function ResultCard({ r, uploadedFolder }: { r: IngestResult; uploadedFolder?: string }) {
  const [showRaw, setShowRaw] = useState(false);
  const ed = r.extracted_data ?? {};
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
              {hasFields && (
                <button
                  onClick={() => setShowRaw((v) => !v)}
                  className="text-xs text-gray-400 hover:text-gray-600"
                >
                  {showRaw ? "Fields" : "Raw JSON"}
                </button>
              )}
            </div>

            {hasFields ? (
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
  text: "Please upload a PDF (or Word / PowerPoint / image) file, or enter a OneDrive folder path, and I'll process it for you.",
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

      {/* Input bar */}
      <div className="shrink-0 bg-white border-t border-gray-200 px-4 py-3">
        <div className="flex items-center gap-2 max-w-2xl mx-auto">
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={busy}
            className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors disabled:opacity-40"
            title="Upload file"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13" />
            </svg>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,.docx,.pptx"
            className="hidden"
            onChange={handleFileChange}
          />
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
            placeholder="Or type a OneDrive folder path, e.g. /Document Processor/In"
            disabled={busy}
            className="flex-1 text-sm border border-gray-200 rounded-xl px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-200 disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={busy || !input.trim()}
            className="p-2 rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14m-7-7l7 7-7 7" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
