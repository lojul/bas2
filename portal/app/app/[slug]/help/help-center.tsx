"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Bot, ChevronDown, Database, Lightbulb, MessagesSquare, Rocket, Search, ShieldCheck, Users } from "lucide-react";
import { HELP_TOPICS, type HelpArticle, type HelpTopic } from "@/lib/help";
import { LEGAL } from "@/lib/legal";

const ICONS: Record<HelpTopic["icon"], typeof Rocket> = {
  start: Rocket,
  data: Database,
  ask: MessagesSquare,
  agents: Bot,
  team: Users,
  account: ShieldCheck,
};

function matches(article: HelpArticle, q: string) {
  return [article.title, article.summary, ...article.body].some((t) => t.toLowerCase().includes(q));
}

function Article({ article, slug, open, onToggle }: { article: HelpArticle; slug: string; open: boolean; onToggle: () => void }) {
  const href = article.link ? (article.link.abs ? article.link.path : `/app/${slug}${article.link.path}`) : null;
  return (
    <li>
      <button type="button" onClick={onToggle} aria-expanded={open} className="flex w-full items-start gap-3 py-3 text-left">
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium">{article.title}</span>
          <span className="block text-xs text-genie-muted">{article.summary}</span>
        </span>
        <ChevronDown size={16} className={`mt-0.5 shrink-0 text-genie-muted transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="space-y-2 pb-4 text-sm leading-relaxed">
          {article.body.map((p) => (
            <p key={p} className={/^\d+\./.test(p) ? "pl-4 -indent-4" : ""}>{p}</p>
          ))}
          {href && (
            <Link href={href} className="inline-block font-medium text-genie-green underline underline-offset-2">
              {article.link!.label} →
            </Link>
          )}
        </div>
      )}
    </li>
  );
}

export function HelpCenter({ slug }: { slug: string }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const q = query.trim().toLowerCase();

  const topics = useMemo(
    () => HELP_TOPICS.map((t) => ({ ...t, articles: q ? t.articles.filter((a) => matches(a, q)) : t.articles })).filter((t) => t.articles.length),
    [q],
  );

  return (
    <div className="space-y-6">
      <label className="relative block max-w-xl">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-genie-muted" />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search help, e.g. Odoo, API key, password"
          className="input pl-9"
        />
      </label>

      {topics.length === 0 ? (
        <p className="text-sm text-genie-muted">Nothing matches &ldquo;{query}&rdquo;. Try another word.</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {topics.map((topic) => {
            const Icon = ICONS[topic.icon];
            return (
              <section key={topic.id} className="card p-5">
                <h2 className="flex items-center gap-2 font-semibold">
                  <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-genie-accent text-genie-green-deep">
                    <Icon size={15} />
                  </span>
                  {topic.title}
                </h2>
                <ul className="mt-2 divide-y divide-genie-border">
                  {topic.articles.map((a) => {
                    const key = `${topic.id}/${a.id}`;
                    return (
                      <Article
                        key={key}
                        article={a}
                        slug={slug}
                        open={open === key || (q !== "" && topic.articles.length === 1)}
                        onToggle={() => setOpen(open === key ? null : key)}
                      />
                    );
                  })}
                </ul>
              </section>
            );
          })}
        </div>
      )}

      <p className="flex items-center gap-2 text-xs text-genie-muted">
        <Lightbulb size={14} /> Tip: if Genie can&apos;t reach a data source, the reason is shown under Settings → Data sources. Still stuck? Email{" "}
        <a href={`mailto:${LEGAL.supportEmail}`} className="underline underline-offset-2">{LEGAL.supportEmail}</a>.
      </p>
    </div>
  );
}
