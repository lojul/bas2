"use client";

import { useRef, useState } from "react";
import { uploadFiles } from "@/lib/api";

interface UploadResult {
  name: string;
  ok: boolean;
  error?: string;
  web_url?: string;
}

export default function UploadPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [selected, setSelected] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState<UploadResult[]>([]);
  const [folder, setFolder] = useState("");
  const [error, setError] = useState("");

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    setResults([]);
    setError("");
    const files = Array.from(e.target.files ?? []).filter((f) =>
      f.name.toLowerCase().endsWith(".pdf")
    );
    setSelected(files);
  }

  async function handleUpload() {
    if (!selected.length) return;
    setUploading(true);
    setError("");
    setResults([]);
    try {
      const data = await uploadFiles(selected);
      setResults(data.results);
      setFolder(data.folder);
      setSelected([]);
      if (inputRef.current) inputRef.current.value = "";
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  const successCount = results.filter((r) => r.ok).length;
  const failCount = results.filter((r) => !r.ok).length;

  return (
    <div className="flex flex-col h-full bg-gray-50">
      <header className="px-6 py-3 bg-white border-b border-gray-200 shrink-0">
        <p className="text-sm font-medium text-gray-700">Upload</p>
        <p className="text-xs text-gray-400">Upload PDFs to OneDrive for automatic processing</p>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-lg space-y-4">
          {/* Drop area */}
          <div
            className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50/30 transition-colors"
            onClick={() => inputRef.current?.click()}
          >
            <p className="text-sm text-gray-600 font-medium">Click to select PDF files</p>
            <p className="text-xs text-gray-400 mt-1">Only PDF files are accepted</p>
            <input
              ref={inputRef}
              type="file"
              accept=".pdf"
              multiple
              className="hidden"
              onChange={handleFileChange}
            />
          </div>

          {/* Selected files */}
          {selected.length > 0 && (
            <div className="bg-white border border-gray-200 rounded-xl divide-y divide-gray-100">
              {selected.map((f, i) => (
                <div key={i} className="flex items-center justify-between px-4 py-2.5 text-sm">
                  <span className="text-gray-800 truncate max-w-xs">{f.name}</span>
                  <span className="text-gray-400 text-xs shrink-0 ml-3">
                    {(f.size / 1024).toFixed(0)} KB
                  </span>
                </div>
              ))}
            </div>
          )}

          {error && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2.5">
              {error}
            </p>
          )}

          {selected.length > 0 && (
            <button
              onClick={handleUpload}
              disabled={uploading}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white rounded-xl py-2.5 text-sm font-medium transition-colors"
            >
              {uploading ? `Uploading ${selected.length} file${selected.length > 1 ? "s" : ""}…` : `Upload ${selected.length} file${selected.length > 1 ? "s" : ""}`}
            </button>
          )}

          {/* Results */}
          {results.length > 0 && (
            <div className="space-y-2">
              {folder && (
                <p className="text-xs text-gray-500">
                  Destination: <span className="font-mono">{folder}</span>
                </p>
              )}
              {successCount > 0 && (
                <p className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-4 py-2.5">
                  {successCount} file{successCount > 1 ? "s" : ""} uploaded. Files will be processed automatically (every 5 min).
                </p>
              )}
              {failCount > 0 && (
                <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-4 py-2.5">
                  {failCount} file{failCount > 1 ? "s" : ""} failed to upload.
                </p>
              )}
              <div className="bg-white border border-gray-200 rounded-xl divide-y divide-gray-100">
                {results.map((r, i) => (
                  <div key={i} className="flex items-center gap-2 px-4 py-2.5 text-sm">
                    <span className={r.ok ? "text-green-600" : "text-red-500"}>
                      {r.ok ? "✓" : "✗"}
                    </span>
                    <span className="text-gray-700 truncate">{r.name}</span>
                    {r.error && <span className="text-xs text-red-500 ml-auto shrink-0">{r.error}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
