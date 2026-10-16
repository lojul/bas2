"use client";

import { useRef, useState, useTransition } from "react";
import { ArrowUp, Building2, FileText, Lightbulb, RotateCcw, Sparkles, UserRound } from "lucide-react";
import { BRAND } from "@/lib/brand";
import { ask } from "./actions";
import { Answer } from "./answer";

// Ask, in the style of Microsoft Copilot (user request 2026-10-16): a centred greeting with one large
// message box and suggestion cards; once a conversation starts, a centred thread with the box kept
// at the bottom. Colours stay in the portal's neutral ERPNext-style theme.

type Turn = { role: "user" | "assistant"; content: string; meta?: string; error?: boolean };
export type Suggestion = { kind: "contact" | "listing" | "document" | "idea"; title: string; prompt: string };

const ICON = { contact: UserRound, listing: Building2, document: FileText, idea: Lightbulb };

function Composer({
  value,
  onChange,
  onSend,
  pending,
  autoFocus,
  big,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  pending: boolean;
  autoFocus: boolean;
  big: boolean;
}) {
  return (
    <form
      className="relative rounded-2xl border border-genie-border bg-white shadow-sm focus-within:border-[#c7c7c7]"
      onSubmit={(e) => {
        e.preventDefault();
        onSend();
      }}
    >
      <textarea
        className={`block w-full resize-none rounded-2xl bg-transparent px-4 pb-12 pt-3.5 text-base outline-none placeholder:text-genie-muted ${big ? "min-h-28" : "min-h-14"}`}
        rows={big ? 3 : 1}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          // Enter sends; Shift+Enter adds a line.
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            onSend();
          }
        }}
        placeholder={`Message ${BRAND.name}…`}
        maxLength={4000}
        aria-label="Your question"
        autoFocus={autoFocus}
      />
      <button
        type="submit"
        disabled={pending || !value.trim()}
        aria-label="Send"
        className="absolute bottom-2.5 right-2.5 flex h-9 w-9 items-center justify-center rounded-full bg-genie-green-deep text-white hover:bg-black disabled:bg-genie-accent disabled:text-genie-muted"
      >
        <ArrowUp size={18} />
      </button>
    </form>
  );
}

// initialQuestion comes from the top bar's "Search or ask" box; it is filled in, ready to send.
export function Chat({ slug, initialQuestion = "", greeting, suggestions }: { slug: string; initialQuestion?: string; greeting: string; suggestions: Suggestion[] }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState(initialQuestion);
  const [pending, start] = useTransition();
  const bottom = useRef<HTMLDivElement>(null);

  function send(text: string) {
    const question = text.trim();
    if (!question || pending) return;
    const next: Turn[] = [...turns, { role: "user", content: question }];
    setTurns(next);
    setInput("");
    requestAnimationFrame(() => bottom.current?.scrollIntoView({ behavior: "smooth" }));
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

  if (turns.length === 0) {
    return (
      <div className="mx-auto flex min-h-[60vh] max-w-3xl flex-col justify-center gap-6 py-6">
        <div className="text-center">
          <span className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-xl border border-genie-border bg-white shadow-sm">
            <Sparkles size={20} />
          </span>
          <h2 className="text-2xl font-semibold">{greeting}</h2>
        </div>
        <Composer value={input} onChange={setInput} onSend={() => send(input)} pending={pending} autoFocus big />
        <div className="grid gap-3 sm:grid-cols-3">
          {suggestions.map((s) => {
            const Icon = ICON[s.kind];
            return (
              <button
                key={s.prompt}
                type="button"
                onClick={() => send(s.prompt)}
                className="rounded-xl border border-genie-border bg-white p-3.5 text-left shadow-sm hover:bg-genie-accent"
              >
                <span className="flex items-center gap-1.5 text-xs font-medium text-genie-muted">
                  <Icon size={14} /> {s.title}
                </span>
                <span className="mt-1.5 block text-sm">{s.prompt}</span>
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col">
      <div className="space-y-5 pb-6">
        {turns.map((t, i) =>
          t.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-genie-accent px-4 py-2.5">{t.content}</div>
            </div>
          ) : (
            <div key={i} className="flex gap-3">
              <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-genie-border bg-white">
                <Sparkles size={14} />
              </span>
              <div className={`min-w-0 flex-1 ${t.error ? "rounded-lg bg-red-50 px-3 py-2 text-red-800" : ""}`}>
                {t.error ? t.content : <Answer text={t.content} />}
                {t.meta && <div className="mt-2 text-xs text-genie-muted">{t.meta}</div>}
              </div>
            </div>
          ),
        )}
        {pending && (
          <div className="flex items-center gap-3 text-sm text-genie-muted">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-genie-border bg-white">
              <Sparkles size={14} className="animate-pulse" />
            </span>
            Looking it up in your data sources…
          </div>
        )}
        <div ref={bottom} />
      </div>
      <div className="sticky bottom-0 space-y-2 bg-white pb-4 pt-2">
        <Composer value={input} onChange={setInput} onSend={() => send(input)} pending={pending} autoFocus={false} big={false} />
        <div className="flex items-center justify-between text-xs text-genie-muted">
          <span>Answers come only from your own systems. Check important facts.</span>
          <button type="button" onClick={() => setTurns([])} className="inline-flex items-center gap-1 hover:text-genie-ink" disabled={pending}>
            <RotateCcw size={12} /> New chat
          </button>
        </div>
      </div>
    </div>
  );
}
