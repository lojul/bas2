"use client";

import { useRef, useState, useTransition } from "react";
import { Send } from "lucide-react";
import { ask } from "./actions";

type Turn = { role: "user" | "assistant"; content: string; meta?: string; error?: boolean };

const EXAMPLES = ["What data do we have?", "Find the contact Wong Mei Ling", "What is our delivery policy?"];

export function Chat({ slug }: { slug: string }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [pending, start] = useTransition();
  const bottom = useRef<HTMLDivElement>(null);

  function send(text: string) {
    const question = text.trim();
    if (!question || pending) return;
    const next: Turn[] = [...turns, { role: "user", content: question }];
    setTurns(next);
    setInput("");
    start(async () => {
      const history = next.filter((t) => !t.error).map(({ role, content }) => ({ role, content }));
      const res = await ask(slug, history);
      setTurns((cur) => [
        ...cur,
        res.ok
          ? {
              role: "assistant",
              content: res.text || "(no answer)",
              meta: `${res.model} · ${res.keySource === "byok" ? "your key" : "platform key"}${
                res.tools.length ? ` · looked up: ${[...new Set(res.tools)].join(", ")}` : ""
              }`,
            }
          : { role: "assistant", content: res.error, error: true },
      ]);
      requestAnimationFrame(() => bottom.current?.scrollIntoView({ behavior: "smooth" }));
    });
  }

  return (
    <div className="flex flex-col gap-4">
      {turns.length === 0 && (
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((q) => (
            <button key={q} type="button" className="btn-secondary text-sm" onClick={() => send(q)}>
              {q}
            </button>
          ))}
        </div>
      )}

      <div className="space-y-3">
        {turns.map((t, i) => (
          <div key={i} className={t.role === "user" ? "flex justify-end" : ""}>
            <div
              className={`max-w-[85%] whitespace-pre-wrap rounded-xl px-4 py-2.5 text-sm ${
                t.role === "user"
                  ? "bg-genie-green-deep text-white"
                  : t.error
                    ? "border border-red-200 bg-red-50 text-red-800"
                    : "border border-genie-border bg-genie-card"
              }`}
            >
              {t.content}
              {t.meta && <div className="mt-2 text-xs text-genie-muted">{t.meta}</div>}
            </div>
          </div>
        ))}
        {pending && <div className="text-sm text-genie-muted">Looking it up…</div>}
        <div ref={bottom} />
      </div>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <input
          className="input flex-1"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about your customers, products, orders or policies…"
          maxLength={4000}
          aria-label="Your question"
        />
        <button type="submit" className="btn" disabled={pending || !input.trim()} aria-label="Send">
          <Send size={16} />
        </button>
      </form>
    </div>
  );
}
