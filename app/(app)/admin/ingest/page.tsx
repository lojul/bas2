"use client";

import { useRef, useState } from "react";
import { processIngest } from "@/lib/api";
import type { IngestResult } from "@/lib/api";

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

function ResultCard({ r }: { r: IngestResult }) {
  const [expanded, setExpanded] = useState(false);
  const ed = r.extracted_data ?? {};

  const highlights: string[] = [];
  if (ed.building_name) highlights.push(String(ed.building_name));
  if (ed.address) highlights.push(String(ed.address));
  if (ed.size_sqft) highlights.push(`${ed.size_sqft} sqft`);
  if (ed.rent_monthly) highlights.push(`HK$${ed.rent_monthly}/mo`);
  if (ed.project_name) highlights.push(String(ed.project_name));
  if (ed.name) highlights.push(String(ed.name));
  if (ed.title) highlights.push(String(ed.title));

  return (
    <div className="mt-2 bg-white border border-gray-200 rounded-xl overflow-hidden text-sm">
      <div className="flex items-start gap-3 px-4 py-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            {r.status === "success" ? (
              <span className="text-green-600 font-medium">✓</span>
            ) : (
              <span className="text-red-500 font-medium">✗</span>
            )}
            <span className="font-medium text-gray-800 truncate">{r.file_name}</span>
            <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${TYPE_COLORS[r.document_type] ?? "bg-gray-100 text-gray-500"}`}>
              {TYPE_LABELS[r.document_type] ?? r.document_type}
            </span>
            {r.confidence > 0 && (
              <span className="text-xs text-gray-400">{Math.round(r.confidence * 100)}%</span>
            )}
          </div>

          {r.status === "error" ? (
            <p className="mt-1 text-xs text-red-500">{r.error}</p>
          ) : (
            <>
              <p className="mt-0.5 text-xs text-gray-400">
                {r.pages} page{r.pages !== 1 ? "s" : ""}
                {r.tables > 0 ? ` · ${r.tables} table${r.tables !== 1 ? "s" : ""}` : ""}
                {r.index_id ? " · Indexed" : ""}
              </p>
              {highlights.length > 0 && (
                <p className="mt-1 text-xs text-gray-600 truncate">{highlights.join(" · ")}</p>
              )}
            </>
          )}
        </div>

        {r.status === "success" && Object.keys(ed).length > 0 && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="shrink-0 text-xs text-gray-400 hover:text-gray-600"
          >
            {expanded ? "Hide" : "Details"}
          </button>
        )}
      </div>

      {expanded && (
        <div className="px-4 pb-3 border-t border-gray-50">
          <pre className="mt-2 text-xs text-gray-600 whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
            {JSON.stringify(ed, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

type Message =
  | { role: "bot"; text: string }
  | { role: "user"; text: string; fileName?: string }
  | { role: "results"; results: IngestResult[] };

const GREETING: Message = {
  role: "bot",
  text: "Please upload a PDF (or Word / PowerPoint / image) file, or enter a OneDrive folder path, and I'll process it for you.",
};

export default function IngestPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [messages, setMessages] = useState<Message[]>([GREETING]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  function push(msg: Message) {
    setMessages((prev) => [...prev, msg]);
  }

  async function run(file?: File, folderPath?: string) {
    if (busy) return;
    setBusy(true);
    push({ role: "bot", text: file ? `Processing ${file.name}…` : `Looking for files in ${folderPath}…` });

    try {
      const data = await processIngest(file, folderPath);

      if (!data.results.length) {
        push({ role: "bot", text: data.message ?? "No supported files found." });
      } else {
        const ok = data.results.filter((r) => r.status === "success").length;
        const total = data.results.length;
        const summary = ok === total
          ? `Done — ${total} file${total !== 1 ? "s" : ""} indexed.`
          : `Done — ${ok}/${total} succeeded.`;
        push({ role: "bot", text: summary });
        push({ role: "results", results: data.results });
      }
    } catch (e: unknown) {
      push({ role: "bot", text: `Error: ${e instanceof Error ? e.message : "Processing failed"}` });
    } finally {
      setBusy(false);
    }
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    push({ role: "user", text: file.name, fileName: file.name });
    if (fileInputRef.current) fileInputRef.current.value = "";
    run(file);
  }

  function handleSend() {
    const path = input.trim();
    if (!path || busy) return;
    setInput("");
    push({ role: "user", text: path });
    run(undefined, path);
  }

  return (
    <div className="flex flex-col h-full bg-gray-50">
      <header className="px-6 py-3 bg-white border-b border-gray-200 shrink-0">
        <p className="text-sm font-medium text-gray-700">Ingest</p>
        <p className="text-xs text-gray-400">Upload a file or enter a OneDrive folder path</p>
      </header>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
        {messages.map((msg, i) => {
          if (msg.role === "results") {
            return (
              <div key={i} className="space-y-2">
                {msg.results.map((r, j) => <ResultCard key={j} r={r} />)}
              </div>
            );
          }
          if (msg.role === "user") {
            return (
              <div key={i} className="flex justify-end">
                <div className="max-w-sm bg-blue-600 text-white text-sm px-4 py-2 rounded-2xl rounded-br-sm">
                  {msg.fileName ? (
                    <span className="flex items-center gap-1.5">
                      <span className="text-blue-200 text-xs">📄</span>
                      {msg.text}
                    </span>
                  ) : (
                    msg.text
                  )}
                </div>
              </div>
            );
          }
          // bot
          return (
            <div key={i} className="flex justify-start">
              <div className="max-w-sm bg-white border border-gray-200 text-gray-700 text-sm px-4 py-2.5 rounded-2xl rounded-bl-sm">
                {msg.text}
                {busy && i === messages.length - 1 && (
                  <span className="ml-1 inline-block w-1 h-3 bg-gray-400 animate-pulse rounded-sm" />
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
