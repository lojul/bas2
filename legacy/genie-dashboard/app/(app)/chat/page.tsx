"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { sendAssistantMessage, clearAssistantSession } from "@/lib/api";

interface AssistantMessage {
  role: "user" | "assistant";
  content: string;
  fileName?: string;
}

function decodeUserId(): string {
  if (typeof window === "undefined") return "dashboard-user";
  const token = localStorage.getItem("token");
  if (token) {
    try {
      const payload = JSON.parse(atob(token.split(".")[1]));
      if (payload?.sub) return String(payload.sub);
    } catch {
      // fall through to generated id
    }
  }
  let id = localStorage.getItem("assistant_user_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("assistant_user_id", id);
  }
  return id;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [input, setInput] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [sending, setSending] = useState(false);
  const [userId, setUserId] = useState("dashboard-user");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setUserId(decodeUserId());
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = useCallback(async () => {
    const body = input.trim();
    if ((!body && !file) || sending) return;

    setInput("");
    const sentFile = file;
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    setSending(true);

    setMessages((prev) => [...prev, { role: "user", content: body, fileName: sentFile?.name }]);

    try {
      const { reply } = await sendAssistantMessage(userId, body, sentFile ?? undefined);
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Assistant error";
      setMessages((prev) => [...prev, { role: "assistant", content: `⚠️ ${msg}` }]);
    } finally {
      setSending(false);
    }
  }, [input, file, sending, userId]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  async function handleClear() {
    await clearAssistantSession(userId).catch(() => {});
    setMessages([]);
  }

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-full bg-gray-50">
      <header className="flex items-center justify-between px-4 lg:px-6 py-3 bg-white border-b border-gray-200 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-medium text-gray-700 truncate">Chat / 文件助手</span>
          <span className="hidden sm:inline text-xs text-gray-400 shrink-0">Powered by Llama 3.3 70B</span>
        </div>
        <button
          onClick={handleClear}
          className="text-xs sm:text-sm text-gray-500 hover:text-gray-700 px-2 sm:px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors shrink-0"
        >
          <span className="hidden sm:inline">New chat / </span>新對話
        </button>
      </header>

      {isEmpty ? (
        <div className="flex-1 flex flex-col items-center justify-center px-4 gap-3 text-center">
          <h2 className="text-xl font-semibold text-gray-800">Document Assistant</h2>
          <p className="text-sm text-gray-500 max-w-md">
            與 WhatsApp / Slack 上的同一個助手 · Same assistant as WhatsApp &amp; Slack
          </p>
          <p className="text-xs text-gray-400 max-w-md">
            貼上樓盤資料或新聞連結，或上傳 PDF / 圖片，助手會幫你建立 Odoo 盤源或知識文章。
            <br />
            Paste listing text or a news link, or attach a PDF/image — the assistant will triage it into an Odoo listing or knowledge article.
          </p>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto px-4 py-4">
          <div className="max-w-2xl mx-auto space-y-4">
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
                    m.role === "user" ? "bg-blue-600 text-white" : "bg-white border border-gray-200 text-gray-800"
                  }`}
                >
                  {m.fileName && (
                    <div className={`text-xs mb-1 ${m.role === "user" ? "text-blue-100" : "text-gray-400"}`}>
                      📎 {m.fileName}
                    </div>
                  )}
                  {m.content || <span className="opacity-50">…</span>}
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex justify-start">
                <div className="max-w-[80%] rounded-2xl px-4 py-3 text-sm bg-white border border-gray-200 text-gray-400">
                  …
                </div>
              </div>
            )}
            <div ref={scrollRef} />
          </div>
        </div>
      )}

      <div className="shrink-0 px-4 pb-4 pt-2 bg-white border-t border-gray-200">
        <div className="max-w-2xl mx-auto space-y-2">
          {file && (
            <div className="flex items-center gap-2 text-xs text-gray-600 bg-gray-100 rounded-lg px-3 py-1.5 w-fit">
              📎 {file.name}
              <button onClick={() => { setFile(null); if (fileInputRef.current) fileInputRef.current.value = ""; }} className="text-gray-400 hover:text-gray-700">
                ✕
              </button>
            </div>
          )}
          <div className="flex gap-3 items-end">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.docx,.pptx"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={sending}
              title="Attach file"
              className="shrink-0 border border-gray-300 rounded-xl px-3 py-3 text-gray-500 hover:bg-gray-50 disabled:opacity-40"
            >
              📎
            </button>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="用中文或英文提問… Enter 發送，Shift+Enter 換行"
              rows={1}
              className="flex-1 resize-none border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 max-h-32 overflow-y-auto"
              disabled={sending}
            />
            <button
              onClick={handleSend}
              disabled={(!input.trim() && !file) || sending}
              className="bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white rounded-xl px-5 py-3 text-sm font-medium transition-colors shrink-0"
            >
              {sending ? "…" : "發送"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
