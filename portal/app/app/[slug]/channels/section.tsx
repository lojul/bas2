import { redirect } from "next/navigation";
import { BRAND } from "@/lib/brand";
import { SITE_URL } from "@/lib/env";
import type { SlackSettings } from "@/lib/slack/slack";
import { createClient, getUser } from "@/lib/supabase/server";
import { canManage, getWorkspace } from "@/lib/workspaces";
import { CopyField, SlackActions, SlackEnabledSwitch, SlackOff } from "./forms";

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
  // C21's existing bot (Azure Function) — offered as the "switched off" target.
  const fallback = slack?.fallback_url ?? (slug === "c21" ? "https://c21net-bas-func-chatbot-slack-ea-prod.azurewebsites.net/api/slack/events" : "");
  const enabled = slack?.enabled !== false;

  return (
    <div className="space-y-4">
      <section className="card">
        {slack ? (
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="font-medium">Slack</h3>
                {enabled ? (
                  <p className="text-sm text-genie-green">On — {BRAND.name}{" "}answers @mentions and direct messages</p>
                ) : (
                  <p className="text-sm text-genie-muted">
                    Off — {slack.fallback_url ? "messages go to the previous bot" : `${BRAND.name} doesn't answer`}
                  </p>
                )}
              </div>
              <SlackEnabledSwitch slug={slug} enabled={enabled} />
            </div>
            <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]">
              <dt className="text-genie-muted">Slack workspace</dt>
              <dd>{slack.team}</dd>
              <dt className="text-genie-muted">Bot</dt>
              <dd>@{slack.bot_name}</dd>
              <dt className="text-genie-muted">When off</dt>
              <dd className="break-all">{slack.fallback_url ? `passes messages to ${slack.fallback_url}` : "stays silent"}</dd>
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
                After this one change, the switch above decides who answers: {BRAND.name}{" "}(on) or the previous bot (off).
              </p>
            </div>
            <SlackActions slug={slug} fallback={fallback} />
          </div>
        ) : (
          <SlackOff slug={slug} fallback={fallback} />
        )}
      </section>
      <p className="text-xs text-genie-muted">WhatsApp and Microsoft Teams come later.</p>
    </div>
  );
}
