import { redirect } from "next/navigation";
import { SITE_URL } from "@/lib/env";
import type { SlackSettings } from "@/lib/slack/slack";
import { createClient, getUser } from "@/lib/supabase/server";
import { canManage, getWorkspace } from "@/lib/workspaces";
import { CopyField, SlackActions, SlackEnabledSwitch, SlackOff, WhatsAppActions, type WhatsAppDefaults, WhatsAppEnabledSwitch, WhatsAppOff } from "./forms";
import type { WhatsAppSettings } from "@/lib/whatsapp/twilio";

// Settings → Channels: where staff can talk to Genie besides the web (Slack now; WhatsApp and
// Teams later).
export async function ChannelsSection({ slug }: { slug: string }) {
  const { user } = await getUser();
  if (!user) redirect("/login");
  const workspace = (await getWorkspace(user.id, slug))!;
  if (!canManage(workspace.role)) return <p className="text-sm text-genie-muted">Only owners and admins can see this page.</p>;

  const supabase = await createClient();
  const { data: tenant } = await supabase.from("tenants").select("settings").eq("id", workspace.id).single<{ settings: { channels?: { slack?: SlackSettings; whatsapp?: WhatsAppSettings } } | null }>();
  const slack = tenant?.settings?.channels?.slack;
  const eventsUrl = `${SITE_URL}/api/slack/${slug}/events`;
  const enabled = slack?.enabled !== false;
  const wa = tenant?.settings?.channels?.whatsapp;
  const waEnabled = wa?.enabled !== false;
  const inboundUrl = `${SITE_URL}/api/whatsapp/${slug}/inbound`;
  // C21: the Twilio Sandbox number and its n8n document intake (the Sandbox's previous webhook).
  const waDefaults: WhatsAppDefaults = {
    accountSid: wa?.account_sid ?? "",
    number: wa?.number ?? (slug === "c21" ? "+14155238886" : ""),
    filesUrl: wa?.files_url ?? (slug === "c21" ? "https://c21net.app.n8n.cloud/webhook/twilio-whatsapp" : ""),
  };

  return (
    <div className="space-y-4">
      <section className="card">
        {slack ? (
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="font-medium">Slack</h3>
                {enabled ? (
                  <p className="text-sm text-genie-green">On — staff can ask in Slack (@mentions and direct messages)</p>
                ) : (
                  <p className="text-sm text-genie-muted">Off — the bot doesn&apos;t answer in Slack. Keys are kept; switch on to resume.</p>
                )}
              </div>
              <SlackEnabledSwitch slug={slug} enabled={enabled} />
            </div>
            <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[max-content_1fr]">
              <dt className="text-genie-muted">Slack workspace</dt>
              <dd>{slack.team}</dd>
              <dt className="text-genie-muted">Bot</dt>
              <dd>@{slack.bot_name}</dd>
            </dl>
            <SlackActions slug={slug}>
              <div className="space-y-2 rounded-lg bg-genie-accent/60 p-4 text-sm">
                <p className="font-medium">Next step, in Slack (api.slack.com/apps → your app):</p>
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
                  This is a one-time change in Slack. After it, the switch above turns Slack on and off.
                </p>
              </div>
            </SlackActions>
          </div>
        ) : (
          <SlackOff slug={slug} />
        )}
      </section>
      <section className="card">
        {wa ? (
          <div className="space-y-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="font-medium">WhatsApp</h3>
                {waEnabled ? (
                  <p className="text-sm text-genie-green">On — text questions to {wa.number} are answered by Genie</p>
                ) : (
                  <p className="text-sm text-genie-muted">Off — Genie doesn&apos;t answer on WhatsApp. Details are kept; switch on to resume.</p>
                )}
              </div>
              <WhatsAppEnabledSwitch slug={slug} enabled={waEnabled} />
            </div>
            <WhatsAppActions slug={slug} d={waDefaults}>
              <div className="space-y-2 rounded-lg bg-genie-accent/60 p-4 text-sm">
                <p className="font-medium">Next step, in Twilio (console.twilio.com → Messaging → Try it out → Send a WhatsApp message → Sandbox settings):</p>
                <ol className="list-decimal space-y-1 pl-5 text-genie-ink/90">
                  <li>
                    <b>When a message comes in</b> → paste, method <b>POST</b>:
                    <div className="mt-1.5">
                      <CopyField value={inboundUrl} />
                    </div>
                  </li>
                  <li>Save. Phones that joined the Sandbox (&quot;join …&quot; code) can now ask by text; photos and files still go to the address above.</li>
                </ol>
                <p className="text-xs text-genie-muted">Sandbox limits: only joined phones, and about 50 messages a day on a trial account.</p>
              </div>
            </WhatsAppActions>
          </div>
        ) : (
          <WhatsAppOff slug={slug} d={waDefaults} />
        )}
      </section>
      <p className="text-xs text-genie-muted">Microsoft Teams comes later.</p>
    </div>
  );
}
