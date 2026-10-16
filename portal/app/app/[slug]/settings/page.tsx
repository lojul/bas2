import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { getUser } from "@/lib/supabase/server";
import { canManage, getWorkspace } from "@/lib/workspaces";
import { AgentsSection } from "../agents/section";
import { KeysSection } from "../keys/section";
import { SourcesSection } from "../sources/section";
import { SettingsTabs } from "./tabs";

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

  return (
    <SettingsTabs
      tabs={[...SECTIONS]}
      panels={{
        "data-sources": <SourcesSection slug={slug} />,
        "ai-keys": <KeysSection slug={slug} />,
        "ai-agents": <AgentsSection slug={slug} />,
      }}
    />
  );
}
