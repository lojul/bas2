"use client";

import { useEffect, useRef } from "react";
import type { ChatMessage } from "@/lib/api";
import { SourcesPanel } from "./SourcesPanel";

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
          isUser
            ? "bg-blue-600 text-white"
            : "bg-white border border-gray-200 text-gray-800"
        }`}
      >
        {msg.content}
        {msg.streaming && (
          <span className="ml-1 inline-block w-2 h-4 bg-gray-400 animate-pulse rounded-sm align-middle" />
        )}
        {!isUser && msg.sources && <SourcesPanel sources={msg.sources} />}
      </div>
    </div>
  );
}

export function ChatMessages({ messages }: { messages: ChatMessage[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (!messages.length) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
        Ask anything about Hong Kong commercial properties
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
      {messages.map((msg, i) => (
        <MessageBubble key={i} msg={msg} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
