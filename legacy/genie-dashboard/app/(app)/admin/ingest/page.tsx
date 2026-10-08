"use client";

import { useEffect, useRef, useState } from "react";
import { clearAssistantSession, sendAssistantMessage } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
  file?: string; // display name of attached file
}

function getOrCreateSessionId(): string {
  let id = sessionStorage.getItem("ingest_session_id");
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem("ingest_session_id", id);
  }
  return id;
}

const URL_RE = /https?:\/\/[^\s<>"]+/g;

function renderWithLinks(text: string, isUser: boolean) {
  const result: React.ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  const re = new RegExp(URL_RE.source, "g");
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) result.push(<span key={last}>{text.slice(last, match.index)}</span>);
    // Strip trailing punctuation that commonly wraps URLs (e.g. Markdown "(url)" or sentence "url.")
    const url = match[0].replace(/[).,;!?]+$/, "");
    const tail = match[0].slice(url.length);
    result.push(
      <a key={match.index} href={url} target="_blank" rel="noopener noreferrer"
        className={`underline ${isUser ? "text-amber-300" : "text-amber-600"}`}>
        {url}
      </a>
    );
    if (tail) result.push(<span key={`${match.index}t`}>{tail}</span>);
    last = match.index + match[0].length;
  }
  if (last < text.length) result.push(<span key={last}>{text.slice(last)}</span>);
  return result;
}

function Bubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}>
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-amber-100 flex items-center justify-center text-xs shrink-0 mr-2 mt-0.5">
          🤖
        </div>
      )}
      <div
        className={`max-w-[78%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap leading-relaxed ${
          isUser
            ? "bg-gray-800 text-white rounded-tr-sm"
            : "bg-white border border-gray-200 text-gray-800 rounded-tl-sm"
        }`}
      >
        {renderWithLinks(msg.content, isUser)}
        {msg.file && (
          <p className="text-xs mt-1 text-gray-400">
            📎 {msg.file}
          </p>
        )}
      </div>
    </div>
  );
}

export default function IngestPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setSessionId(getOrCreateSessionId());
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send() {
    if ((!input.trim() && !file) || loading || !sessionId) return;

    const userMsg: Message = {
      role: "user",
      content: input.trim(),
      file: file?.name,
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    const sentFile = file;
    setFile(null);
    setLoading(true);

    // Placeholder assistant bubble while waiting
    setMessages((prev) => [...prev, { role: "assistant", content: "…" }]);

    try {
      const { reply } = await sendAssistantMessage(sessionId, userMsg.content, sentFile ?? undefined);
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: "assistant", content: reply };
        return updated;
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Error";
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: "assistant", content: `❌ ${msg}` };
        return updated;
      });
    } finally {
      setLoading(false);
      textRef.current?.focus();
    }
  }

  async function handleReset() {
    if (!sessionId) return;
    await clearAssistantSession(sessionId).catch(() => {});
    const newId = crypto.randomUUID();
    sessionStorage.setItem("ingest_session_id", newId);
    setSessionId(newId);
    setMessages([]);
    setInput("");
    setFile(null);
    if (fileRef.current) fileRef.current.value = "";
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="flex flex-col h-full bg-gray-50">
      <header className="px-6 py-3 bg-white border-b border-gray-200 shrink-0 flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-700">Ingest Assistant <span className="text-xs font-normal text-gray-400 ml-1">Qwen 2.5 72B</span></p>
          <p className="text-xs text-gray-400">Knowledge 知識文章 · Property Listing 物業盤源 · CRM</p>
        </div>
        <button
          onClick={handleReset}
          className="text-xs text-gray-400 hover:text-gray-600 px-2 py-1 rounded hover:bg-gray-100"
        >
          Reset
        </button>
      </header>

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {messages.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center h-full text-center text-gray-400 gap-2">
            <span className="text-3xl">🤖</span>
            <p className="text-sm text-gray-400">Type a message or attach a file to get started.</p>
            <p className="text-sm text-gray-400">輸入訊息或附上檔案開始使用。</p>
            <p className="text-sm text-gray-400">1 · Knowledge 知識文章 &nbsp;|&nbsp; 2 · CRM &nbsp;|&nbsp; 3 · Property Listing 物業盤源</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <Bubble key={i} msg={msg} />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* File preview */}
      {file && (
        <div className="mx-4 mb-1 flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-lg px-3 py-2 text-xs text-blue-700">
          <span>📎 {file.name}</span>
          <button onClick={() => setFile(null)} className="ml-auto text-blue-400 hover:text-blue-600">✕</button>
        </div>
      )}

      {/* Input bar */}
      <div className="shrink-0 border-t border-gray-200 bg-white px-4 py-3 flex items-end gap-2">
        <button
          onClick={() => fileRef.current?.click()}
          className="shrink-0 w-9 h-9 flex items-center justify-center rounded-full text-gray-400 hover:text-gray-600 hover:bg-gray-100"
          title="Attach file"
        >
          📎
        </button>
        <input
          ref={fileRef}
          type="file"
          className="hidden"
          accept=".pdf,.jpg,.jpeg,.png,.docx,.pptx"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <textarea
          ref={textRef}
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
          className="flex-1 resize-none rounded-2xl border border-gray-200 px-4 py-2.5 text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-300 max-h-32 overflow-y-auto"
          style={{ minHeight: "2.5rem" }}
          disabled={loading}
        />
        <button
          onClick={send}
          disabled={loading || (!input.trim() && !file)}
          className="shrink-0 w-9 h-9 flex items-center justify-center rounded-full bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {loading ? (
            <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
          ) : (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 19V5m0 0l-7 7m7-7l7 7" />
            </svg>
          )}
        </button>
      </div>
    </div>
  );
}
