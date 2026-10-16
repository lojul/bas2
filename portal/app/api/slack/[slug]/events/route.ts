import { after } from "next/server";
import { askAgent } from "@/lib/ai/agent";
import type { ChatTurn } from "@/lib/ai/gateway";
import { slackApi, slackWorkspace, stripMentions, toSlackMrkdwn, verifySlackSignature } from "@/lib/slack/slack";

// Slack Event Subscriptions endpoint for one Genie workspace:
//   https://genie.infiniduo.com/api/slack/<workspace slug>/events
// Answers @mentions in channels (in a thread) and direct messages. Slack wants an answer within
// 3 seconds, so the request is acknowledged at once and the question is answered in after().

export const dynamic = "force-dynamic";
// The answer runs after the acknowledgement; give it the same time as Ask.
export const maxDuration = 120;

type SlackEvent = {
  type: string;
  subtype?: string;
  channel: string;
  channel_type?: string;
  user?: string;
  bot_id?: string;
  text?: string;
  ts: string;
  thread_ts?: string;
};

type Workspace = NonNullable<Awaited<ReturnType<typeof slackWorkspace>>>;

async function answer(ws: Workspace, ev: SlackEvent) {
  const isDm = ev.channel_type === "im";
  const threadTs = ev.thread_ts ?? (isDm ? undefined : ev.ts);
  const question = stripMentions(ev.text ?? "");
  if (!question) {
    await slackApi(ws.token, "chat.postMessage", { channel: ev.channel, thread_ts: threadTs, text: "Ask me about your company's data — contacts, listings, documents…" });
    return;
  }

  const placeholder = await slackApi<{ ts?: string }>(ws.token, "chat.postMessage", {
    channel: ev.channel,
    thread_ts: threadTs,
    text: "⏳ Looking it up…",
  });

  // Earlier turns of a thread give the question context; read from Slack, nothing stored in Genie.
  let history: ChatTurn[] = [{ role: "user", content: question }];
  if (ev.thread_ts) {
    const replies = await slackApi<{ messages?: SlackEvent[] }>(ws.token, "conversations.replies", { channel: ev.channel, ts: ev.thread_ts, limit: 20 });
    if (replies.ok && replies.messages?.length) {
      history = replies.messages
        .filter((m) => m.ts !== placeholder.ts && !(m.text ?? "").startsWith("⏳"))
        .map((m) => ({
          role: m.bot_id || (ws.slack.bot_user_id && m.user === ws.slack.bot_user_id) ? ("assistant" as const) : ("user" as const),
          content: stripMentions(m.text ?? ""),
        }))
        .filter((m) => m.content);
      if (history.at(-1)?.role !== "user") history.push({ role: "user", content: question });
    }
  }

  let text: string;
  try {
    const result = await askAgent(null, { id: ws.id, name: ws.name }, null, history, { channel: "slack" });
    text = toSlackMrkdwn(result.text || "(no answer)");
  } catch (e) {
    text = `Sorry — I couldn't answer that: ${e instanceof Error ? e.message : String(e)}`;
  }
  if (placeholder.ok && placeholder.ts) {
    await slackApi(ws.token, "chat.update", { channel: ev.channel, ts: placeholder.ts, text });
  } else {
    await slackApi(ws.token, "chat.postMessage", { channel: ev.channel, thread_ts: threadTs, text });
  }
}

export async function POST(request: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const raw = await request.text();
  const ws = await slackWorkspace(slug);
  if (!ws) return new Response("Slack is not connected for this workspace.", { status: 404 });
  if (!verifySlackSignature(ws.signingSecret, request.headers.get("x-slack-request-timestamp"), request.headers.get("x-slack-signature"), raw)) {
    return new Response("Invalid signature.", { status: 401 });
  }

  const body = JSON.parse(raw) as { type: string; challenge?: string; event?: SlackEvent };
  if (body.type === "url_verification") return Response.json({ challenge: body.challenge });

  // Slack switched off in Settings → Channels: acknowledge and ignore.
  if (ws.slack.enabled === false) return new Response("ok");
  // Slack retries when it thinks we were slow; the first delivery is already being answered.
  if (request.headers.get("x-slack-retry-num")) return new Response("ok");

  const ev = body.event;
  if (body.type === "event_callback" && ev && !ev.bot_id && !ev.subtype) {
    const isMention = ev.type === "app_mention";
    const isDm = ev.type === "message" && ev.channel_type === "im";
    if (isMention || isDm) after(() => answer(ws, ev).catch((e) => console.error("slack answer failed", e)));
  }
  return new Response("ok");
}
