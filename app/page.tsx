import {
  Sparkles,
  MessageSquareMore,
  FileScan,
  Search,
  BookOpenText,
  ContactRound,
  Languages,
  ArrowRight,
  ArrowDown,
  Building2,
} from "lucide-react";

const SIGN_IN_URL = "/login";
const CONTACT_URL = "mailto:hello@infiniduo.com";

function Wordmark() {
  return (
    <a href="/" className="flex items-center gap-2">
      <span className="flex size-8 items-center justify-center rounded-full bg-genie-ink text-white">
        <Sparkles className="size-4" />
      </span>
      <span className="font-serif italic text-2xl tracking-tight text-genie-ink">Genie</span>
    </a>
  );
}

function ChatPreview() {
  const listings = [
    { name: "Prosperity Tower 嘉兆商業大廈", size: "1,280 sq ft", rent: "HK$48/ft²" },
    { name: "The Center 中環中心", size: "2,050 sq ft", rent: "HK$55/ft²" },
    { name: "Nexxus Building 協成行中心", size: "860 sq ft", rent: "HK$41/ft²" },
  ];
  return (
    <div className="relative">
      <div className="absolute -top-10 -right-8 size-40 rounded-full bg-genie-green/20 blur-3xl" aria-hidden />
      <div className="absolute -bottom-12 -left-10 size-48 rounded-full bg-genie-accent/60 blur-3xl" aria-hidden />

      <div className="relative rounded-3xl border border-genie-border bg-genie-card p-5 shadow-[0_24px_64px_-20px_rgba(22,36,28,0.22)]">
        <div className="flex items-center justify-between border-b border-genie-border pb-3">
          <div className="flex items-center gap-2">
            <span className="size-2.5 rounded-full bg-red-400/70" />
            <span className="size-2.5 rounded-full bg-amber-400/70" />
            <span className="size-2.5 rounded-full bg-genie-green/70" />
          </div>
          <span className="text-xs font-medium text-genie-muted">Genie · WhatsApp</span>
        </div>

        <div className="mt-4 space-y-3 text-sm leading-relaxed">
          <div className="flex justify-end">
            <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-genie-accent px-4 py-2.5 text-genie-accent-fg">
              <p className="font-noto-tc">中環有咩寫字樓出租？</p>
              <p className="mt-1 text-right text-[10px] text-genie-accent-fg/60">10:42 ✓✓</p>
            </div>
          </div>

          <div className="flex items-start gap-2.5">
            <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-genie-ink text-white">
              <Sparkles className="size-3.5" />
            </span>
            <div className="max-w-[85%] space-y-2.5 rounded-2xl rounded-tl-sm bg-[#f1efe6] px-4 py-3 text-genie-ink">
              <p>Found 3 offices for lease in Central — here are the top matches:</p>

              <div className="space-y-2">
                {listings.map((l) => (
                  <div
                    key={l.name}
                    className="flex items-center gap-3 rounded-xl border border-genie-border bg-genie-card px-3 py-2.5"
                  >
                    <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-genie-accent text-genie-accent-fg">
                      <Building2 className="size-4" />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-[13px] font-semibold font-noto-tc">{l.name}</p>
                      <p className="text-xs text-genie-muted">
                        {l.size} · {l.rent}
                      </p>
                    </div>
                  </div>
                ))}
              </div>

              <p className="text-xs text-genie-muted">
                Sample preview only — not real client data. Want details on any of these?
              </p>
              <p className="text-right text-[10px] text-genie-muted">10:42</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

const steps = [
  {
    title: "Send it in",
    body: "Forward a document, photo, or question over WhatsApp, Slack, or the dashboard — no special app needed.",
  },
  {
    title: "Genie reads it",
    body: "OCR, classification, and extraction happen automatically; Genie pulls out the structured details.",
  },
  {
    title: "It's in sync",
    body: "Listings, contacts, and knowledge articles land straight in your CRM, searchable instantly.",
  },
];

const features = [
  {
    icon: MessageSquareMore,
    title: "Any channel, one brain",
    body: "WhatsApp, Slack, and web dashboard all talk to the same assistant — no duplicate setup, no inconsistent answers.",
  },
  {
    icon: FileScan,
    title: "Instant document intake",
    body: "Drop in a PDF, photo, or forwarded listing and Genie OCRs, classifies, and extracts the structured data automatically.",
  },
  {
    icon: Search,
    title: "Natural-language property search",
    body: "Ask in plain Chinese or English — “中環有咩寫字樓出租？” — and get real, grounded results back, powered by semantic search.",
  },
  {
    icon: BookOpenText,
    title: "Knowledge that builds itself",
    body: "Market news and research get saved as searchable knowledge articles automatically, no manual filing.",
  },
  {
    icon: ContactRound,
    title: "Business cards to contacts",
    body: "Snap a name card and it's a CRM contact — no retyping.",
  },
  {
    icon: Languages,
    title: "Bilingual by default",
    body: "Full support for Traditional Chinese and English, side by side.",
  },
];

export default function Home() {
  return (
    <div className="min-h-screen bg-genie-bg font-sans text-genie-ink antialiased">
      <header className="sticky top-0 z-40 border-b border-genie-border bg-genie-bg/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
          <Wordmark />
          <nav className="hidden items-center gap-7 text-sm font-medium text-genie-muted md:flex">
            <a href="#how-it-works" className="transition-colors hover:text-genie-ink">
              How it works
            </a>
            <a href="#features" className="transition-colors hover:text-genie-ink">
              Features
            </a>
          </nav>
          <a
            href={SIGN_IN_URL}
            className="rounded-full bg-genie-ink px-5 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:bg-genie-green-deep hover:shadow-md"
          >
            Sign in
          </a>
        </div>
      </header>

      <section className="relative overflow-hidden">
        <div className="mx-auto grid max-w-6xl items-center gap-14 px-5 pt-16 pb-20 sm:pt-24 lg:grid-cols-2 lg:gap-10">
          <div>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-genie-border bg-genie-card px-3.5 py-1.5 text-xs font-semibold tracking-wide text-genie-green-deep">
              <Sparkles className="size-3.5" />
              AI for property businesses
            </span>
            <h1 className="mt-6 text-5xl leading-[1.05] font-bold tracking-tight sm:text-6xl">
              One AI assistant for every way your business{" "}
              <em className="font-serif italic text-genie-green-deep">talks</em>
            </h1>
            <p className="mt-6 max-w-lg text-lg leading-relaxed text-genie-muted">
              Genie ingests documents and answers property questions over WhatsApp, Slack, and the
              web — one shared AI assistant, always in sync.
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-4">
              <a
                href={SIGN_IN_URL}
                className="inline-flex items-center gap-2 rounded-full bg-genie-ink px-7 py-3.5 text-sm font-medium text-white shadow-sm transition-all hover:bg-genie-green-deep hover:shadow-md"
              >
                Sign in <ArrowRight className="size-4" />
              </a>
              <a
                href="#how-it-works"
                className="inline-flex items-center gap-2 rounded-full border border-genie-border bg-genie-card px-6 py-3.5 text-sm font-medium text-genie-ink transition-colors hover:bg-genie-accent"
              >
                See how it works <ArrowDown className="size-4" />
              </a>
            </div>
            <p className="mt-8 text-sm text-genie-muted">
              Built for real-estate teams · <span className="font-noto-tc">繁體中文</span>{" "}
              &amp; English
            </p>
          </div>

          <ChatPreview />
        </div>
      </section>

      <section id="how-it-works" className="scroll-mt-20 border-y border-genie-border bg-[#f1efe6]/60">
        <div className="mx-auto max-w-6xl px-5 py-20 sm:py-24">
          <p className="text-sm font-semibold tracking-widest text-genie-green-deep uppercase">
            How it works
          </p>
          <h2 className="mt-3 max-w-xl text-3xl font-bold tracking-tight sm:text-4xl">
            From inbox to insight in <em className="font-serif italic text-genie-green-deep">three steps</em>
          </h2>

          <div className="mt-12 grid gap-5 md:grid-cols-3">
            {steps.map((step, i) => (
              <div
                key={step.title}
                className="rounded-3xl border border-genie-border bg-genie-card p-7 shadow-[0_1px_2px_rgba(22,36,28,0.06),0_12px_40px_-12px_rgba(22,36,28,0.14)]"
              >
                <span className="font-serif text-5xl text-genie-green italic">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <h3 className="mt-5 text-xl font-semibold">{step.title}</h3>
                <p className="mt-2.5 leading-relaxed text-genie-muted">{step.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="features" className="scroll-mt-20">
        <div className="mx-auto max-w-6xl px-5 py-20 sm:py-24">
          <p className="text-sm font-semibold tracking-widest text-genie-green-deep uppercase">
            Features
          </p>
          <h2 className="mt-3 max-w-2xl text-3xl font-bold tracking-tight sm:text-4xl">
            Everything your property business <em className="font-serif italic text-genie-green-deep">wishes</em> for
          </h2>

          <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {features.map((f) => (
              <div
                key={f.title}
                className="group rounded-3xl border border-genie-border bg-genie-card p-7 shadow-[0_1px_2px_rgba(22,36,28,0.06),0_12px_40px_-12px_rgba(22,36,28,0.14)] transition-shadow hover:shadow-[0_2px_4px_rgba(22,36,28,0.05),0_24px_64px_-20px_rgba(22,36,28,0.22)]"
              >
                <span className="flex size-11 items-center justify-center rounded-2xl bg-genie-accent text-genie-accent-fg transition-colors group-hover:bg-genie-green group-hover:text-white">
                  <f.icon className="size-5" />
                </span>
                <h3 className="mt-5 text-lg font-semibold">{f.title}</h3>
                <p className="mt-2 text-[15px] leading-relaxed text-genie-muted">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="px-5 pb-24">
        <div className="mx-auto max-w-6xl overflow-hidden rounded-[2.5rem] bg-genie-ink px-6 py-16 text-center text-white shadow-[0_2px_4px_rgba(22,36,28,0.05),0_24px_64px_-20px_rgba(22,36,28,0.22)] sm:py-20">
          <Sparkles className="mx-auto size-8 text-genie-green" />
          <h2 className="mx-auto mt-5 max-w-xl text-3xl font-bold tracking-tight sm:text-4xl">
            Ready to put Genie to work?
          </h2>
          <p className="mx-auto mt-4 max-w-md text-white/70">
            One assistant across every channel — your team can start today.
          </p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-4">
            <a
              href={SIGN_IN_URL}
              className="inline-flex items-center gap-2 rounded-full bg-genie-card px-7 py-3.5 text-sm font-medium text-genie-ink transition-colors hover:bg-genie-bg"
            >
              Sign in <ArrowRight className="size-4" />
            </a>
            <a
              href={CONTACT_URL}
              className="text-sm font-medium text-white/80 underline-offset-4 transition-colors hover:text-white hover:underline"
            >
              Contact us
            </a>
          </div>
        </div>
      </section>

      <footer className="border-t border-genie-border">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-5 py-10 sm:flex-row">
          <Wordmark />
          <p className="text-sm text-genie-muted">
            © 2026 Genie by{" "}
            <a
              href="https://infiniduo.com"
              className="font-medium text-genie-ink underline-offset-4 hover:underline"
            >
              infiniduo
            </a>
            . All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}
