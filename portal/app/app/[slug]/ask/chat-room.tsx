"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { ArrowUp, Building2, FileText, Lightbulb, Lock, Sparkles, Trash2, UserRound, Users } from "lucide-react";
import { createClient } from "@/lib/supabase/browser";
import type { ProposalView } from "@/lib/odoo/changes";
import { type ChatMessage, createChat, deleteChat, loadProposals, postMessage } from "./actions";
import { Answer } from "./answer";
import { ProposalCard } from "./proposal-card";

// Ask with saved chats (decided 2026-10-17), in the style of Microsoft Copilot. The chat list lives in
// the main sidebar under Ask; this is the conversation, with live updates from the other members.
// Team chats: Genie answers when someone writes @Genie. Private chats: Genie answers every message.

export type ChatSummary = { id: string; title: string; visibility: "team" | "private"; created_by: string | null };
export type Suggestion = { kind: "contact" | "listing" | "document" | "idea"; title: string; prompt: string };

const ICON = { contact: UserRound, listing: Building2, document: FileText, idea: Lightbulb };

function Composer({
  value,
  onChange,
  onSend,
  pending,
  big,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  pending: boolean;
  big: boolean;
  placeholder: string;
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
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            onSend();
          }
        }}
        placeholder={placeholder}
        maxLength={4000}
        aria-label="Your message"
        autoFocus
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

function VisibilityToggle({ value, onChange }: { value: "team" | "private"; onChange: (v: "team" | "private") => void }) {
  return (
    <div className="inline-flex rounded-lg border border-genie-border p-0.5 text-sm">
      {(["private", "team"] as const).map((v) => (
        <button
          key={v}
          type="button"
          onClick={() => onChange(v)}
          className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1 ${value === v ? "bg-genie-accent font-medium text-genie-ink" : "text-genie-muted hover:text-genie-ink"}`}
        >
          {v === "team" ? <Users size={14} /> : <Lock size={14} />} {v === "team" ? "Team" : "Private"}
        </button>
      ))}
    </div>
  );
}

function Message({
  m,
  meId,
  team,
  cards,
}: {
  m: ChatMessage;
  meId: string;
  team: boolean;
  cards?: React.ReactNode;
}) {
  if (m.role === "assistant") {
    return (
      <div className="flex gap-3">
        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-genie-border bg-white">
          <Sparkles size={14} />
        </span>
        <div className={`min-w-0 flex-1 ${m.meta?.error ? "rounded-lg bg-red-50 px-3 py-2 text-red-800" : ""}`}>
          {m.meta?.error ? m.content : <Answer text={m.content} />}
          {cards}
          {m.meta?.model && (
            <div className="mt-2 text-xs text-genie-muted">
              {m.meta.model} · {m.meta.key_source === "byok" ? "your key" : "platform key"}
              {m.meta.tools?.length ? ` · looked up: ${m.meta.tools.join(", ")}` : ""}
            </div>
          )}
        </div>
      </div>
    );
  }
  const mine = m.author_id === meId;
  return (
    <div className={mine ? "flex justify-end" : "flex"}>
      <div className="max-w-[85%]">
        {team && !mine && <div className="mb-1 text-xs text-genie-muted">{m.author_email}</div>}
        <div className={`whitespace-pre-wrap rounded-2xl px-4 py-2.5 ${mine ? "bg-genie-accent" : "border border-genie-border bg-white"}`}>{m.content}</div>
      </div>
    </div>
  );
}

export function ChatRoom({
  slug,
  me,
  chat,
  initialMessages,
  canDelete,
  initialProposals = [],
  greeting,
  suggestions,
  initialQuestion = "",
}: {
  slug: string;
  me: { id: string; email: string };
  chat: ChatSummary | null;
  initialMessages: ChatMessage[];
  canDelete: boolean;
  initialProposals?: ProposalView[];
  greeting: string;
  suggestions: Suggestion[];
  initialQuestion?: string;
}) {
  const router = useRouter();
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState(initialQuestion);
  const [visibility, setVisibility] = useState<"team" | "private">("private");
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [pending, start] = useTransition();
  const [proposals, setProposals] = useState<Record<string, ProposalView>>(() => Object.fromEntries(initialProposals.map((p) => [p.id, p])));
  const putProposals = (list: ProposalView[]) => setProposals((cur) => ({ ...cur, ...Object.fromEntries(list.map((p) => [p.id, p])) }));
  const bottom = useRef<HTMLDivElement>(null);
  const chatId = chat?.id ?? null;
  const team = chat?.visibility === "team";

  // Live: messages from the other members (and Genie's answers to them) appear without a refresh.
  useEffect(() => {
    if (!chatId) return;
    const supabase = createClient();
    const channel = supabase
      .channel(`chat:${chatId}`)
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "chat_messages", filter: `chat_id=eq.${chatId}` }, (payload) => {
        const m = payload.new as ChatMessage;
        setMessages((cur) => (cur.some((x) => x.id === m.id) ? cur : [...cur, m]));
        // A draft change made for someone else's message: fetch its card.
        if (m.meta?.proposals?.length) void loadProposals(slug, m.meta.proposals).then(putProposals);
      })
      .subscribe();
    return () => {
      void supabase.removeChannel(channel);
    };
  }, [chatId, slug]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, thinking]);

  const add = (list: (ChatMessage | null)[]) =>
    setMessages((cur) => [...cur, ...list.filter((m): m is ChatMessage => !!m && !cur.some((x) => x.id === m.id))]);

  function send(text: string) {
    const content = text.trim();
    if (!content || pending) return;
    setError(null);
    setInput("");
    start(async () => {
      let id = chatId;
      if (!id) {
        // First message of a new chat: the chat is named after it.
        const created = await createChat(slug, content.split("\n")[0].slice(0, 60), visibility);
        if (!created.ok) {
          setError(created.error);
          setInput(content);
          return;
        }
        id = created.id;
      }
      const willAsk = !chatId ? visibility === "private" || /@genie\b/i.test(content) : !team || /@genie\b/i.test(content);
      setThinking(willAsk);
      const res = await postMessage(slug, id, content);
      setThinking(false);
      if (!res.ok) {
        setError(res.error);
        setInput(content);
        return;
      }
      if (!chatId) {
        // No router.refresh() here: it cancels this navigation and leaves "Starting the chat…" up for
        // good. createChat already revalidated the page, so the sidebar lists the new chat.
        router.push(`/app/${slug}/ask?chat=${id}`);
        return;
      }
      putProposals(res.proposals);
      add([res.mine, res.answer]);
      router.refresh();
    });
  }

  // New chat: greeting, Private/Team, big box, suggestions.
  if (!chat) {
    return (
      <div className="flex">
        <div className="mx-auto flex min-h-[60vh] max-w-3xl flex-1 flex-col justify-center gap-5 py-6">
          <div className="text-center">
            <span className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-xl border border-genie-border bg-white shadow-sm">
              <Sparkles size={20} />
            </span>
            <h2 className="text-2xl font-semibold">{greeting}</h2>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-3 text-sm text-genie-muted">
            <VisibilityToggle value={visibility} onChange={setVisibility} />
            {visibility === "team" && <span>Write @Genie to ask Genie</span>}
          </div>
          <Composer
            value={input}
            onChange={setInput}
            onSend={() => send(input)}
            pending={pending}
            big
            placeholder={visibility === "team" ? "Write to your team — add @Genie to ask Genie…" : "Message Genie…"}
          />
          {error && <p className="text-sm text-genie-danger">{error}</p>}
          <div className="grid gap-3 sm:grid-cols-3">
            {suggestions.map((s) => {
              const Icon = ICON[s.kind];
              const prompt = visibility === "team" ? `@Genie ${s.prompt}` : s.prompt;
              return (
                <button
                  key={s.prompt}
                  type="button"
                  onClick={() => send(prompt)}
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
          {pending && <p className="animate-pulse text-center text-sm text-genie-muted">Starting the chat…</p>}
        </div>
      </div>
    );
  }

  return (
    <div className="flex">
      <div className="mx-auto flex max-w-3xl flex-1 flex-col">
        <div className="mb-4 flex items-center justify-between gap-3 border-b border-genie-border pb-3">
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold">{chat.title}</h2>
            <p className="flex items-center gap-1.5 text-xs text-genie-muted">
              {team ? <Users size={12} /> : <Lock size={12} />}
              {team ? "Team chat — everyone in the workspace · write @Genie to ask Genie" : "Private — only you · Genie answers every message"}
            </p>
          </div>
          {canDelete &&
            (confirmDelete ? (
              <span className="flex shrink-0 items-center gap-2 text-sm">
                <span className="text-genie-muted">Delete this chat for everyone?</span>
                <button
                  type="button"
                  className="btn-secondary px-3 py-1 text-genie-danger"
                  onClick={async () => {
                    const res = await deleteChat(slug, chat.id);
                    if (res.ok) router.push(`/app/${slug}/ask`);
                    else setError(res.error ?? "Could not delete.");
                  }}
                >
                  Delete
                </button>
                <button type="button" className="text-genie-muted underline underline-offset-2" onClick={() => setConfirmDelete(false)}>
                  Cancel
                </button>
              </span>
            ) : (
              <button type="button" className="btn-danger shrink-0" onClick={() => setConfirmDelete(true)} title="Delete chat">
                <Trash2 size={14} /> Delete
              </button>
            ))}
        </div>
        <div className="space-y-5 pb-6">
          {messages.length === 0 && <p className="text-sm text-genie-muted">No messages yet.</p>}
          {messages.map((m) => (
            <Message
              key={m.id}
              m={m}
              meId={me.id}
              team={team}
              cards={m.meta?.proposals
                ?.filter((id) => proposals[id])
                .map((id) => (
                  <ProposalCard key={id} slug={slug} view={proposals[id]} onChange={(v) => putProposals([v])} />
                ))}
            />
          ))}
          {thinking && (
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
          <Composer
            value={input}
            onChange={setInput}
            onSend={() => send(input)}
            pending={pending}
            big={false}
            placeholder={team ? "Message the team — add @Genie to ask Genie…" : "Message Genie…"}
          />
          {error && <p className="text-sm text-genie-danger">{error}</p>}
          <p className="text-xs text-genie-muted">Answers come only from your own systems. Check important facts.</p>
        </div>
      </div>
    </div>
  );
}
