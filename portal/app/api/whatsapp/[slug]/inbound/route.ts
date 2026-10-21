import { after } from "next/server";
import { askAgent } from "@/lib/ai/agent";
import { BRAND } from "@/lib/brand";
import { SITE_URL } from "@/lib/env";
import { completeLink, LINK_MESSAGE, memberByPhone } from "@/lib/whatsapp/links";
import { sendWhatsApp, toWhatsAppText, verifyTwilioSignature, whatsappWorkspace } from "@/lib/whatsapp/twilio";

// Twilio "A message comes in" webhook for one Genie workspace:
//   https://genie.infiniduo.com/api/whatsapp/<workspace slug>/inbound
// Text from a member's linked number → answered by Genie (sent back through Twilio's API after the
// acknowledgement). "LINK <code>" → links the number. Other numbers → told how to link, no data.
// Photo or file → passed on unchanged to the workspace's files address (C21: n8n document intake).

export const dynamic = "force-dynamic";
export const maxDuration = 120;

const EMPTY_TWIML = new Response("<Response/>", { headers: { "Content-Type": "text/xml" } });
const twiml = () => EMPTY_TWIML.clone();
const xml = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
// A short reply straight in the webhook answer (no separate send).
const reply = (text: string) => new Response(`<Response><Message>${xml(text)}</Message></Response>`, { headers: { "Content-Type": "text/xml" } });

export async function POST(request: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const raw = await request.text();
  const form = new URLSearchParams(raw);
  const ws = await whatsappWorkspace(slug);
  if (!ws) return new Response("WhatsApp is not connected for this workspace.", { status: 404 });

  // Twilio signs the public address it posted to.
  const url = `${SITE_URL}/api/whatsapp/${slug}/inbound`;
  if (!verifyTwilioSignature(ws.token, url, form, request.headers.get("x-twilio-signature"))) {
    return new Response("Invalid signature.", { status: 403 });
  }
  if (ws.wa.enabled === false) return twiml();

  // Files keep going to the existing document intake.
  if (Number(form.get("NumMedia") ?? "0") > 0) {
    if (!ws.wa.files_url) return twiml();
    try {
      const res = await fetch(ws.wa.files_url, {
        method: "POST",
        headers: { "Content-Type": request.headers.get("content-type") ?? "application/x-www-form-urlencoded" },
        body: raw,
        signal: AbortSignal.timeout(10_000),
      });
      return new Response(await res.text(), { status: res.status, headers: { "Content-Type": res.headers.get("content-type") ?? "text/xml" } });
    } catch (e) {
      console.error("whatsapp files forward failed", e);
      return twiml();
    }
  }

  const from = form.get("From") ?? "";
  const question = (form.get("Body") ?? "").trim();
  const phone = from.replace(/^whatsapp:/, "");
  if (!phone || !question) return twiml();

  // "LINK 123456" from the Members page ties this number to a member.
  const code = LINK_MESSAGE.exec(question)?.[1];
  if (code) return reply(await completeLink(ws.id, phone, code));

  // Only linked members get answers: anyone else could otherwise read the workspace's data.
  const member = await memberByPhone(ws.id, phone);
  if (!member) {
    return reply(
      `This WhatsApp number isn't linked to ${ws.name} in ${BRAND.name}. Sign in at ${SITE_URL}, open Members → Your WhatsApp → Link WhatsApp, and send the code shown there.`,
    );
  }
  after(async () => {
    let text: string;
    try {
      const result = await askAgent(null, { id: ws.id, name: ws.name }, null, [{ role: "user", content: question.slice(0, 4000) }], { channel: "whatsapp" });
      text = toWhatsAppText(result.text || "(no answer)");
    } catch (e) {
      text = `Sorry — I couldn't answer that: ${e instanceof Error ? e.message : String(e)}`;
    }
    await sendWhatsApp(ws.wa.account_sid!, ws.token, ws.wa.number!, from, text);
  });
  return twiml();
}
