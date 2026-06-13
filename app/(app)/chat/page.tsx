"use client";

import { useState, useCallback, useRef } from "react";
import { streamMessage, clearConversation, generateReport } from "@/lib/api";
import type { ChatMessage, Source } from "@/lib/api";
import { ChatMessages } from "@/components/ChatMessages";

const SAMPLE_QUESTIONS = [
  { en: "Office space for rent in Central?", zh: "中環有哪些寫字樓出租？" },
  { en: "Retail shops available in Causeway Bay?", zh: "銅鑼灣有什麼零售舖位？" },
  { en: "Market trend for commercial properties in 2025?", zh: "2025年商業樓市走勢如何？" },
  { en: "Compare office rents in Quarry Bay vs Kwun Tong", zh: "鰂魚涌與觀塘辦公室租金比較" },
];

function getOrCreateThreadId(): string {
  let tid = localStorage.getItem("thread_id");
  if (!tid) {
    tid = crypto.randomUUID();
    localStorage.setItem("thread_id", tid);
  }
  return tid;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [threadId, setThreadId] = useState<string>(() =>
    typeof window !== "undefined" ? getOrCreateThreadId() : ""
  );
  const abortRef = useRef<(() => void) | null>(null);

  const sendQuestion = useCallback((question: string) => {
    if (!question.trim() || streaming) return;

    setInput("");
    setStreaming(true);

    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setMessages((prev) => [...prev, { role: "assistant", content: "", streaming: true }]);

    const abort = streamMessage(
      question,
      threadId,
      (chunk) => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last?.role === "assistant") {
            updated[updated.length - 1] = { ...last, content: last.content + chunk };
          }
          return updated;
        });
      },
      (sources: Source[], finalThreadId: string) => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last?.role === "assistant") {
            updated[updated.length - 1] = { ...last, streaming: false, sources };
          }
          return updated;
        });
        localStorage.setItem("thread_id", finalThreadId);
        setThreadId(finalThreadId);
        setStreaming(false);
      },
      (err) => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last?.role === "assistant") {
            updated[updated.length - 1] = { ...last, content: `Error: ${err}`, streaming: false };
          }
          return updated;
        });
        setStreaming(false);
      },
    );
    abortRef.current = abort;
  }, [streaming, threadId]);

  const handleSend = useCallback(() => {
    sendQuestion(input.trim());
  }, [input, sendQuestion]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  async function handleClear() {
    if (streaming) abortRef.current?.();
    await clearConversation(threadId).catch(() => {});
    const newId = crypto.randomUUID();
    localStorage.setItem("thread_id", newId);
    setThreadId(newId);
    setMessages([]);
    setStreaming(false);
  }

  const allSources: Source[] = messages
    .filter((m) => m.role === "assistant" && m.sources && m.sources.length > 0)
    .flatMap((m) => m.sources!);

  const handleGenerateReport = useCallback(async () => {
    if (allSources.length === 0) return;
    setReportLoading(true);
    try {
      const blob = await generateReport(allSources);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "property_report.pdf";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Report generation failed");
    } finally {
      setReportLoading(false);
    }
  }, [allSources]);

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-full bg-gray-50">
      <header className="flex items-center justify-between px-6 py-3 bg-white border-b border-gray-200 shrink-0">
        <span className="text-sm font-medium text-gray-700">Chat / 搜尋助手</span>
        <div className="flex items-center gap-2">
          {allSources.length > 0 && (
            <button
              onClick={handleGenerateReport}
              disabled={reportLoading}
              className="text-sm text-blue-600 hover:text-blue-800 px-3 py-1.5 rounded-lg hover:bg-blue-50 transition-colors disabled:opacity-40"
            >
              {reportLoading ? "生成中…" : "生成報告 PDF"}
            </button>
          )}
          <button
            onClick={handleClear}
            className="text-sm text-gray-500 hover:text-gray-700 px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors"
          >
            New chat / 新對話
          </button>
        </div>
      </header>

      {isEmpty ? (
        <div className="flex-1 flex flex-col items-center justify-center px-4 gap-8">
          <div className="text-center space-y-1">
            <h2 className="text-xl font-semibold text-gray-800">Property Intelligence Assistant</h2>
            <p className="text-sm text-gray-500">香港商業物業搜尋助手 · Ask in English or 中文</p>
          </div>

          <div className="w-full max-w-2xl grid grid-cols-1 sm:grid-cols-2 gap-3">
            {SAMPLE_QUESTIONS.map((q, i) => (
              <button
                key={i}
                onClick={() => sendQuestion(q.zh)}
                disabled={streaming}
                className="text-left px-4 py-3 bg-white border border-gray-200 rounded-xl hover:border-blue-400 hover:bg-blue-50 transition-colors group disabled:opacity-40"
              >
                <p className="text-sm font-medium text-gray-800 group-hover:text-blue-700">{q.zh}</p>
                <p className="text-xs text-gray-400 mt-0.5">{q.en}</p>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <ChatMessages messages={messages} />
      )}

      <div className="shrink-0 px-4 pb-4 pt-2 bg-white border-t border-gray-200">
        <div className="max-w-3xl mx-auto flex gap-3 items-end">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="用中文或英文提問… Enter 發送，Shift+Enter 換行"
            rows={1}
            className="flex-1 resize-none border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 max-h-32 overflow-y-auto"
            disabled={streaming}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || streaming}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white rounded-xl px-5 py-3 text-sm font-medium transition-colors shrink-0"
          >
            {streaming ? "…" : "發送"}
          </button>
        </div>
      </div>
    </div>
  );
}
