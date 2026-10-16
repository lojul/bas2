import { redirect } from "next/navigation";
import { BRAND } from "@/lib/brand";
import { SITE_URL } from "@/lib/env";
import type { SlackSettings } from "@/lib/slack/slack";
import { createClient, getUser } from "@/lib/supabase/server";
import { canManage, getWorkspace } from "@/lib/workspaces";
import { CopyField, SlackActions, SlackOff, SlackOffSwitch } from "./forms";

// Settings → Channels: where staff can talk to Genie besides the web (Slack now; WhatsApp and
// Teams later).
export async function ChannelsSection({ slug }: { slug: string }) {
  const { user } = await getUser();
  if (!user) redirect("/login");
  const workspace = (await getWorkspace(user.id, slug))!;
  if (!canManage(workspace.role)) return <p className="text-sm text-genie-muted">Only owners and admins can see this page.</p>;

  const supabase = await createClient();
  const { data: tenant } = await supabase.from("tenants").select("settings").eq("id", workspace.id).single<{ settings: { channels?: { slack?: SlackSettings } } | null }>();
  const slack = tenant?.settings?.channels?.slack;
  const eventsUrl = `${SITE_URL}/api/slack/${slug}/events`;

  return (
    <div className="space-y-4">
      <section className="card">
        {slack ? (
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="font-medium">Slack</h3>
                <p className="text-sm text-genie-green">On — answers @mentions and direct messages</p>
              </div>
              <SlackOffSwitch slug={slug} />
            </div>
            <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]">
              <dt className="text-genie-muted">Slack workspace</dt>
              <dd>{slack.team}</dd>
              <dt className="text-genie-muted">Bot</dt>
              <dd>@{slack.bot_name}</dd>
            </dl>
            <div className="space-y-2 rounded-lg bg-genie-accent/60 p-4 text-sm">
              <p className="font-medium">Last step, in Slack (api.slack.com/apps → your app):</p>
              <ol className="list-decimal space-y-1 pl-5 text-genie-ink/90">
                <li>
                  <b>Event Subscriptions</b> → Enable → Request URL:
                  <div className="mt-1.5">
                    <CopyField value={eventsUrl} />
                  </div>
                </li>
                <li>Subscribe to bot events <code className="font-mono">app_mention</code> and <code className="font-mono">message.im</code> → Save.</li>
                <li>
                  <b>OAuth &amp; Permissions</b> → scopes <code className="font-mono">app_mentions:read</code>, <code className="font-mono">chat:write</code>,{" "}
                  <code className="font-mono">im:history</code>, <code className="font-mono">channels:history</code> → reinstall the app if Slack asks.
                </li>
                <li>
                  <b>App Home</b> → allow users to send messages. Then @mention the bot in a channel, or message it directly.
                </li>
              </ol>
              <p className="text-xs text-genie-muted">
                Pointing an existing bot here moves it to {BRAND.name}: its old server stops receiving messages. Switching back is the same
                Request URL change.
              </p>
            </div>
            <SlackActions slug={slug} />
          </div>
        ) : (
          <SlackOff slug={slug} />
        )}
      </section>
      <p className="text-xs text-genie-muted">WhatsApp and Microsoft Teams come later.</p>
    </div>
  );
}
