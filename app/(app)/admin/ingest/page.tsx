"use client";

import { useRef, useState } from "react";
import { triageFile, uploadFiles } from "@/lib/api";
import type { TriageResult } from "@/lib/api";

const ACCEPTED_EXTS = ".pdf,.jpg,.jpeg,.png,.docx,.pptx";

const TYPE_LABELS: Record<string, string> = {
  listing: "Single Listing",
  listing_list: "Multi Listing",
  pitching_deck: "Pitching Deck",
  news: "News",
  contact: "Name Card",
  unknown: "Unknown",
  unsupported: "Not Supported",
};

type FileStatus = "triaging" | "ready" | "unsupported" | "uploading" | "done" | "error";

interface FileItem {
  id: string;
  file: File;
  status: FileStatus;
  triage?: TriageResult;
  uploadError?: string;
}

function TypeBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    listing: "bg-blue-50 text-blue-700",
    listing_list: "bg-blue-50 text-blue-700",
    pitching_deck: "bg-purple-50 text-purple-700",
    news: "bg-yellow-50 text-yellow-700",
    contact: "bg-green-50 text-green-700",
    unknown: "bg-gray-100 text-gray-600",
  };
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${colors[type] ?? "bg-gray-100 text-gray-600"}`}>
      {TYPE_LABELS[type] ?? type}
    </span>
  );
}

function FileRow({
  item,
  onRemove,
}: {
  item: FileItem;
  onRemove: (id: string) => void;
}) {
  const sizeKb = (item.file.size / 1024).toFixed(0);

  return (
    <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-50 last:border-0">
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-800 truncate">{item.file.name}</p>
        <div className="mt-0.5 flex items-center gap-2 flex-wrap">
          {item.status === "triaging" && (
            <span className="text-xs text-gray-400 flex items-center gap-1">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-gray-400 animate-pulse" />
              Analysing…
            </span>
          )}
          {item.status === "ready" && item.triage && (
            <>
              <span className="text-xs text-green-600 font-medium">✓ Ready</span>
              <TypeBadge type={item.triage.detected_type} />
              {item.triage.confidence > 0 && (
                <span className="text-xs text-gray-400">
                  {Math.round(item.triage.confidence * 100)}%
                </span>
              )}
            </>
          )}
          {item.status === "unsupported" && (
            <span className="text-xs text-amber-600">
              {item.triage?.reason ?? "Not supported"}
            </span>
          )}
          {item.status === "uploading" && (
            <span className="text-xs text-blue-500 animate-pulse">Uploading…</span>
          )}
          {item.status === "done" && (
            <span className="text-xs text-green-600 font-medium">✓ Queued in OneDrive</span>
          )}
          {item.status === "error" && (
            <span className="text-xs text-red-500">
              ✗ {item.uploadError ?? "Failed"}
            </span>
          )}
        </div>
      </div>

      <span className="text-xs text-gray-400 shrink-0">{sizeKb} KB</span>

      {(item.status === "ready" || item.status === "unsupported" || item.status === "done" || item.status === "error") && (
        <button
          onClick={() => onRemove(item.id)}
          className="text-gray-300 hover:text-gray-500 shrink-0 text-sm leading-none"
          title="Remove"
        >
          ✕
        </button>
      )}
    </div>
  );
}

export default function IngestPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<FileItem[]>([]);
  const [processing, setProcessing] = useState(false);

  function updateItem(id: string, patch: Partial<FileItem>) {
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, ...patch } : it)));
  }

  async function addFiles(files: File[]) {
    if (!files.length) return;
    const newItems: FileItem[] = files.map((f) => ({
      id: `${f.name}-${f.lastModified}-${Math.random()}`,
      file: f,
      status: "triaging" as const,
    }));
    setItems((prev) => [...prev, ...newItems]);

    await Promise.all(
      newItems.map(async (item) => {
        try {
          const result = await triageFile(item.file);
          updateItem(item.id, {
            triage: result,
            status: result.can_process ? "ready" : "unsupported",
          });
        } catch {
          updateItem(item.id, {
            status: "unsupported",
            triage: {
              file_name: item.file.name,
              can_process: false,
              detected_type: "unknown",
              format: "",
              confidence: 0,
              reason: "Analysis failed — check API connection",
            },
          });
        }
      })
    );
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    addFiles(files);
    if (inputRef.current) inputRef.current.value = "";
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    addFiles(Array.from(e.dataTransfer.files));
  }

  async function handleProcess() {
    const readyItems = items.filter((it) => it.status === "ready");
    if (!readyItems.length) return;
    setProcessing(true);
    readyItems.forEach((it) => updateItem(it.id, { status: "uploading" }));

    try {
      const data = await uploadFiles(readyItems.map((it) => it.file));
      for (const result of data.results) {
        const item = readyItems.find((it) => it.file.name === result.name);
        if (item) {
          updateItem(item.id, {
            status: result.ok ? "done" : "error",
            uploadError: result.error,
          });
        }
      }
    } catch (e: unknown) {
      readyItems.forEach((it) =>
        updateItem(it.id, {
          status: "error",
          uploadError: e instanceof Error ? e.message : "Upload failed",
        })
      );
    } finally {
      setProcessing(false);
    }
  }

  const triagingCount = items.filter((it) => it.status === "triaging").length;
  const readyCount = items.filter((it) => it.status === "ready").length;
  const doneCount = items.filter((it) => it.status === "done").length;
  const unsupportedCount = items.filter((it) => it.status === "unsupported").length;

  return (
    <div className="flex flex-col h-full bg-gray-50">
      <header className="px-6 py-3 bg-white border-b border-gray-200 shrink-0">
        <p className="text-sm font-medium text-gray-700">Ingest</p>
        <p className="text-xs text-gray-400">
          Drop documents — AI analyses type before processing
        </p>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-2xl space-y-4">
          {/* Drop zone */}
          <div
            className="border-2 border-dashed border-gray-300 rounded-xl p-10 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50/30 transition-colors"
            onClick={() => inputRef.current?.click()}
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
          >
            <p className="text-sm text-gray-600 font-medium">Click or drag files here</p>
            <p className="text-xs text-gray-400 mt-1">PDF · Word · PowerPoint · JPG · PNG</p>
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPTED_EXTS}
              multiple
              className="hidden"
              onChange={handleFileChange}
            />
          </div>

          {/* File list */}
          {items.length > 0 && (
            <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2 border-b border-gray-100">
                <span className="text-xs text-gray-500">
                  {items.length} file{items.length !== 1 ? "s" : ""}
                  {triagingCount > 0 && ` · analysing ${triagingCount}…`}
                </span>
                <button
                  onClick={() => setItems([])}
                  className="text-xs text-gray-400 hover:text-gray-600"
                >
                  Clear all
                </button>
              </div>
              {items.map((item) => (
                <FileRow
                  key={item.id}
                  item={item}
                  onRemove={(id) => setItems((prev) => prev.filter((it) => it.id !== id))}
                />
              ))}
            </div>
          )}

          {/* Actions — only show once triage is done */}
          {items.length > 0 && triagingCount === 0 && (
            <div className="space-y-2">
              {readyCount > 0 && (
                <button
                  onClick={handleProcess}
                  disabled={processing}
                  className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white rounded-xl py-2.5 text-sm font-medium transition-colors"
                >
                  {processing
                    ? "Uploading…"
                    : `Process ${readyCount} file${readyCount !== 1 ? "s" : ""} →`}
                </button>
              )}
              {unsupportedCount > 0 && (
                <p className="text-xs text-amber-600 text-center">
                  {unsupportedCount} file{unsupportedCount !== 1 ? "s" : ""} not supported yet — logged for future development
                </p>
              )}
              {doneCount > 0 && (
                <p className="text-xs text-green-600 text-center">
                  {doneCount} file{doneCount !== 1 ? "s" : ""} queued in OneDrive — pipeline runs automatically every 5 min
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
