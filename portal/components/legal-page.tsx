import { Logo } from "@/components/logo";
import { SiteFooter } from "@/components/site-footer";
import { LEGAL } from "@/lib/legal";

// Shared layout for /privacy and /terms. Children are <section>s with h2/p/ul content.
export function LegalPage({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-6 py-10">
      <header>
        <Logo />
      </header>
      <article
        className="mt-10 space-y-8 text-sm leading-relaxed [&_a]:underline [&_a]:underline-offset-2 [&_h2]:mb-2 [&_h2]:text-base [&_h2]:font-semibold [&_li]:mt-1 [&_p]:mt-2 [&_ul]:mt-2 [&_ul]:list-disc [&_ul]:pl-5"
      >
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
          <p className="text-genie-muted">Last updated {LEGAL.lastUpdated}</p>
        </div>
        {children}
      </article>
      <SiteFooter />
    </main>
  );
}
