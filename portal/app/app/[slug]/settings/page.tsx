import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { getUser } from "@/lib/supabase/server";
import { canManage, getWorkspace } from "@/lib/workspaces";
import { AgentsSection } from "../agents/section";
import { KeysSection } from "../keys/section";
import { SourcesSection } from "../sources/section";

export const metadata: Metadata = { title: "Settings" };
// Turning Odoo on checks the connection with Odoo inside this page's server action.
export const maxDuration = 60;

const SECTIONS = [
  { id: "data-sources", title: "Data sources", hint: "Systems Genie reads live when someone asks. Nothing is copied into Genie." },
  { id: "ai-keys", title: "AI model keys", hint: "Optional: your own Anthropic, OpenRouter or xAI key instead of the platform key." },
  { id: "ai-agents", title: "AI agent access (MCP)", hint: "API keys that let Claude, ChatGPT or your own agents read this workspace." },
] as const;

export default async function SettingsPage({ params }: PageProps<"/app/[slug]/settings">) {
  const { slug } = await params;
  const { user } = await getUser();
  if (!user) redirect("/login");
  const workspace = await getWorkspace(user.id, slug);
  if (!workspace) redirect("/app");
  if (!canManage(workspace.role)) {
    return <p className="text-sm text-genie-muted">Only owners and admins can change settings.</p>;
  }

  const body = { "data-sources": SourcesSection, "ai-keys": KeysSection, "ai-agents": AgentsSection };
  return (
    <div className="space-y-10">
      <nav className="flex flex-wrap gap-2 text-sm">
        {SECTIONS.map((s) => (
          <a key={s.id} href={`#${s.id}`} className="rounded-full border border-genie-border px-3 py-1 hover:bg-genie-card">
            {s.title}
          </a>
        ))}
      </nav>
      {SECTIONS.map((s) => {
        const Section = body[s.id];
        return (
          <section key={s.id} id={s.id} className="scroll-mt-6 space-y-4">
            <div className="border-b border-genie-border pb-2">
              <h2 className="text-lg font-semibold">{s.title}</h2>
              <p className="text-sm text-genie-muted">{s.hint}</p>
            </div>
            <Section slug={slug} />
          </section>
        );
      })}
    </div>
  );
}
