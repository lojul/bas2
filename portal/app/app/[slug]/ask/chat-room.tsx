"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { ArrowUp, Building2, FileDown, FileText, Lightbulb, Lock, Sparkles, Trash2, UserRound, Users } from "lucide-react";
import { createClient } from "@/lib/supabase/browser";
import type { ProposalView } from "@/lib/odoo/changes";
import { type ChatMessage, createChat, deleteChat, loadProposals, postMessage } from "./actions";
import { Answer } from "./answer";
import { downloadAnswerPdf } from "./answer-pdf";
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
  pdf,
}: {
  m: ChatMessage;
  meId: string;
  team: boolean;
  cards?: React.ReactNode;
  pdf?: { title: string; workspaceName: string };
}) {
  const answerRef = useRef<HTMLDivElement>(null);
  if (m.role === "assistant") {
    return (
      <div className="flex gap-3">
        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-genie-border bg-white">
          <Sparkles size={14} />
        </span>
        <div className={`min-w-0 flex-1 ${m.meta?.error ? "rounded-lg bg-red-50 px-3 py-2 text-red-800" : ""}`}>
          {m.meta?.error ? (
            m.content
          ) : (
            <div ref={answerRef}>
              <Answer text={m.content} />
            </div>
          )}
          {cards}
          {(m.meta?.model || (pdf && !m.meta?.error)) && (
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-genie-muted">
              {m.meta?.model && (
                <span>
                  {m.meta.model} · {m.meta.key_source === "byok" ? "your key" : "platform key"}
                  {m.meta.tools?.length ? ` · looked up: ${m.meta.tools.join(", ")}` : ""}
                </span>
              )}
              {pdf && !m.meta?.error && (
                <button
                  type="button"
                  onClick={() => answerRef.current && downloadAnswerPdf({ answerEl: answerRef.current, ...pdf })}
                  className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-genie-ink hover:bg-genie-accent"
                  title="Lay this answer out as a page and save it as a PDF"
                >
                  <FileDown size={13} /> Download PDF
                </button>
              )}
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
  workspaceName,
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
  workspaceName: string;
}) {
  const router = useRouter();
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState(initialQuestion);
  const [visibility, setVisibility] = useState<"team" | "private">("private");
  // What Genie is doing, shown as Genie's turn in the conversation ("Starting the chat…", "Looking it up…").
  const [status, setStatus] = useState<string | null>(null);
  // A new chat being started: the conversation shows right away, before the chat exists.
  const [draft, setDraft] = useState<ChatSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [pending, start] = useTransition();
  const [proposals, setProposals] = useState<Record<string, ProposalView>>(() => Object.fromEntries(initialProposals.map((p) => [p.id, p])));
  const putProposals = (list: ProposalView[]) => setProposals((cur) => ({ ...cur, ...Object.fromEntries(list.map((p) => [p.id, p])) }));
  const bottom = useRef<HTMLDivElement>(null);
  const chatId = chat?.id ?? null;
  const view = chat ?? draft;
  const team = view?.visibility === "team";

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
  }, [messages.length, status]);

  function send(text: string) {
    const content = text.trim();
    if (!content || pending) return;
    setError(null);
    setInput("");
    // The message shows in the conversation at once; replaced by the saved one when it comes back.
    const temp: ChatMessage = {
      id: `pending-${Date.now()}`,
      role: "user",
      author_id: me.id,
      author_email: me.email,
      content,
      meta: {},
      created_at: new Date().toISOString(),
    };
    setMessages((cur) => [...cur, temp]);
    if (!chatId) {
      setDraft({ id: "", title: content.split("\n")[0].slice(0, 60), visibility, created_by: me.id });
      setStatus("Starting the chat…");
    }
    const fail = (message: string) => {
      setMessages((cur) => cur.filter((m) => m.id !== temp.id));
      setStatus(null);
      setDraft(null);
      setError(message);
      setInput(content);
    };
    start(async () => {
      let id = chatId;
      if (!id) {
        // First message of a new chat: the chat is named after it.
        const created = await createChat(slug, content.split("\n")[0].slice(0, 60), visibility);
        if (!created.ok) return fail(created.error);
        id = created.id;
      }
      const willAsk = !chatId ? visibility === "private" || /@genie\b/i.test(content) : !team || /@genie\b/i.test(content);
      if (willAsk) setStatus("Looking it up in your data sources…");
      const res = await postMessage(slug, id, content);
      if (!res.ok) return fail(res.error);
      setStatus(null);
      putProposals(res.proposals);
      setMessages((cur) => {
        const rest = cur.filter((m) => m.id !== temp.id && m.id !== res.mine.id);
        return [...rest, res.mine, ...(res.answer && !rest.some((m) => m.id === res.answer!.id) ? [res.answer] : [])];
      });
      if (!chatId) {
        // No router.refresh() here: it cancels this navigation and the page never moves on.
        // createChat already revalidated the page, so the sidebar lists the new chat.
        router.push(`/app/${slug}/ask?chat=${id}`);
        return;
      }
      router.refresh();
    });
  }

  // New chat: greeting, Private/Team, big box, suggestions.
  if (!view) {
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
        </div>
      </div>
    );
  }

  return (
    <div className="flex">
      <div className="mx-auto flex max-w-3xl flex-1 flex-col">
        <div className="mb-4 flex items-center justify-between gap-3 border-b border-genie-border pb-3">
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold">{view.title}</h2>
            <p className="flex items-center gap-1.5 text-xs text-genie-muted">
              {team ? <Users size={12} /> : <Lock size={12} />}
              {team ? "Team chat — everyone in the workspace · write @Genie to ask Genie" : "Private — only you · Genie answers every message"}
            </p>
          </div>
          {canDelete &&
            chat &&
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
          {messages.length === 0 && !status && <p className="text-sm text-genie-muted">No messages yet.</p>}
          {messages.map((m, i) => {
            // Download PDF only under an answer to a question that asked for a PDF (user 2026-10-19).
            const question = m.role === "assistant" ? messages.slice(0, i).findLast((x) => x.role === "user")?.content : undefined;
            return (
              <Message
                key={m.id}
                m={m}
                meId={me.id}
                team={team}
                pdf={question && /pdf/i.test(question) ? { title: question.split("\n")[0].slice(0, 120), workspaceName } : undefined}
                cards={m.meta?.proposals
                  ?.filter((id) => proposals[id])
                  .map((id) => (
                    <ProposalCard key={id} slug={slug} view={proposals[id]} onChange={(v) => putProposals([v])} />
                  ))}
              />
            );
          })}
          {status && (
            <div className="flex items-center gap-3 text-sm text-genie-muted">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-genie-border bg-white">
                <Sparkles size={14} className="animate-pulse" />
              </span>
              {status}
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
