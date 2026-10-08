"use client";

import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "@/lib/api";
import { SourcesPanel } from "./SourcesPanel";

function ThumbButton({
  icon,
  active,
  disabled,
  onClick,
}: {
  icon: string;
  active: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={icon === "👍" ? "Good answer" : "Wrong answer"}
      className={`text-sm px-1.5 py-0.5 rounded transition-colors ${
        active
          ? "opacity-100"
          : "opacity-30 hover:opacity-60"
      } disabled:cursor-default`}
    >
      {icon}
    </button>
  );
}

function MessageBubble({
  msg,
  index,
  onFeedback,
}: {
  msg: ChatMessage;
  index: number;
  onFeedback?: (messageIndex: number, rating: "up" | "down") => void;
}) {
  const isUser = msg.role === "user";
  const [rated, setRated] = useState<"up" | "down" | null>(null);

  function handleRate(rating: "up" | "down") {
    if (rated) return;
    setRated(rating);
    onFeedback?.(index, rating);
  }

  const showFeedback = !isUser && !msg.streaming && msg.content && onFeedback;

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
        {showFeedback && (
          <div className="flex gap-0.5 mt-2 -mb-0.5">
            <ThumbButton
              icon="👍"
              active={rated === "up"}
              disabled={rated !== null}
              onClick={() => handleRate("up")}
            />
            <ThumbButton
              icon="👎"
              active={rated === "down"}
              disabled={rated !== null}
              onClick={() => handleRate("down")}
            />
          </div>
        )}
      </div>
    </div>
  );
}

export function ChatMessages({
  messages,
  onFeedback,
}: {
  messages: ChatMessage[];
  onFeedback?: (messageIndex: number, rating: "up" | "down") => void;
}) {
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
        <MessageBubble key={i} msg={msg} index={i} onFeedback={onFeedback} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
