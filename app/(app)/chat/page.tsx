"use client";

import { useState, useCallback, useRef } from "react";
import { streamMessage, clearConversation } from "@/lib/api";
import type { ChatMessage, Source } from "@/lib/api";
import { ChatMessages } from "@/components/ChatMessages";

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
  const [threadId, setThreadId] = useState<string>(() =>
    typeof window !== "undefined" ? getOrCreateThreadId() : ""
  );
  const abortRef = useRef<(() => void) | null>(null);

  const handleSend = useCallback(() => {
    const question = input.trim();
    if (!question || streaming) return;

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
  }, [input, streaming, threadId]);

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

  return (
    <div className="flex flex-col h-full bg-gray-50">
      <header className="flex items-center justify-between px-6 py-3 bg-white border-b border-gray-200 shrink-0">
        <span className="text-sm font-medium text-gray-700">Chat</span>
        <button
          onClick={handleClear}
          className="text-sm text-gray-500 hover:text-gray-700 px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors"
        >
          New chat
        </button>
      </header>

      <ChatMessages messages={messages} />

      <div className="shrink-0 px-4 pb-4 pt-2 bg-white border-t border-gray-200">
        <div className="max-w-3xl mx-auto flex gap-3 items-end">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about Hong Kong commercial properties… (Enter to send, Shift+Enter for newline)"
            rows={1}
            className="flex-1 resize-none border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 max-h-32 overflow-y-auto"
            disabled={streaming}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || streaming}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white rounded-xl px-5 py-3 text-sm font-medium transition-colors shrink-0"
          >
            {streaming ? "…" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
