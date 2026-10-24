import type { Metadata } from "next";
import Link from "next/link";
import { LegalPage } from "@/components/legal-page";
import { BRAND } from "@/lib/brand";
import { LEGAL } from "@/lib/legal";

export const metadata: Metadata = { title: "Privacy Policy" };

export default function PrivacyPage() {
  const name = BRAND.name;
  return (
    <LegalPage title="Privacy Policy">
      <section>
        <p>
          This policy explains how {LEGAL.entity}{" "}(&ldquo;we&rdquo;, &ldquo;us&rdquo;) handles personal data when you
          use {name}, including this website and the {name}{" "}assistant on the web, Slack, WhatsApp, Microsoft Teams and
          through the {name}{" "}MCP server (together, the &ldquo;Service&rdquo;). We follow the Personal Data (Privacy)
          Ordinance (Cap. 486) of Hong Kong (the &ldquo;PDPO&rdquo;).
        </p>
      </section>

      <section>
        <h2>1. Two roles: your account, and your company&apos;s data</h2>
        <ul>
          <li>
            <strong>Account data.</strong> For the personal data you give us to use the Service (for example your email
            address), we decide how it is used and we are responsible for it.
          </li>
          <li>
            <strong>Customer data.</strong>{" "}A company that subscribes (the &ldquo;Customer&rdquo;) connects its own
            systems, such as databases, spreadsheets, Odoo or documents, and its staff ask questions about that data.
            The Customer decides what is connected and who has access. For this data we act only on the Customer&apos;s
            instructions, as a data processor in the sense of the PDPO. If your personal data is in a Customer&apos;s
            system and you have a question about it, please contact that company first.
          </li>
        </ul>
      </section>

      <section>
        <h2>2. What we collect</h2>
        <ul>
          <li><strong>Account and workspace details:</strong> your email address, the workspaces you belong to, your role, invitations you send or receive, and sign-in records.</li>
          <li><strong>Customer data:</strong> records and documents read from the systems a Customer connects, the text and search index we build from them, and the questions staff ask and the answers given.</li>
          <li><strong>Keys and connection details:</strong> AI provider keys and connector credentials a Customer saves. These are stored encrypted in a secrets vault. Only the workspace&apos;s owners and admins can display or copy a saved key, one key at a time, when they ask for it.</li>
          <li><strong>Changes in Odoo:</strong> when a workspace switches this on, a change Genie prepares (for example a new lead&apos;s name and phone number) is held as a draft until someone confirms or cancels it, at most 24 hours; after that only who asked, who confirmed, what kind of change and which Odoo record are kept, for one year.</li>
          <li><strong>Chats:</strong> messages people write on Ask and Genie&apos;s answers, which can include details read from the Customer&apos;s systems. Team chats are visible to all members of the workspace, private chats only to their author. Chats are deleted automatically 90 days after their last message and can be deleted earlier by their author or a workspace owner or admin. On WhatsApp, a member&apos;s recent messages and Genie&apos;s answers are kept for 30 minutes so Genie can follow the conversation, then deleted automatically. We do not otherwise keep copies of the Customer&apos;s records.</li>
          <li><strong>Usage records:</strong> counts of messages, AI tokens, tool calls and pages read by text recognition (OCR), used for billing and plan limits.</li>
          <li><strong>Billing details:</strong> handled by our payment provider, Stripe. We do not store card numbers.</li>
          <li><strong>Technical data:</strong> server logs (such as IP address, browser type and time of request) kept for security and troubleshooting.</li>
        </ul>
      </section>

      <section>
        <h2>3. How we use it</h2>
        <ul>
          <li>To provide the Service: sign you in, run your workspace, answer questions over your company&apos;s data by reading your connected systems at the moment a question is asked. We do not keep a copy of the records we read, apart from what appears in saved chats (see above).</li>
          <li>To bill for the Service and enforce plan limits.</li>
          <li>To keep the Service secure, prevent abuse and fix problems.</li>
          <li>To contact you about your account, security, or changes to the Service.</li>
        </ul>
        <p>
          We do not sell personal data, and we do not use Customer data to train AI models. We will not use your
          personal data for direct marketing without your consent.
        </p>
      </section>

      <section>
        <h2>4. AI providers</h2>
        <p>
          To answer a question, the relevant text is sent to an AI model provider. By default we use our own account
          with providers such as Anthropic, OpenRouter, xAI or Microsoft Azure OpenAI. If a Customer saves its own key
          (&ldquo;bring your own key&rdquo;), requests go to that provider under the Customer&apos;s own agreement with
          them. For our own account we choose providers and settings that do not allow the provider to train on the
          data we send.
        </p>
      </section>

      <section>
        <h2>5. Who else processes data for us</h2>
        <p>We use these service providers, each bound to protect the data and use it only to provide their service to us:</p>
        <ul>
          <li><strong>Supabase:</strong> database, sign-in, file storage and secrets vault (hosted in {LEGAL.hosting}).</li>
          <li><strong>Vercel:</strong> website hosting.</li>
          <li><strong>Stripe:</strong> payments and invoices.</li>
          <li><strong>AI model providers:</strong> as described in section 4.</li>
          <li><strong>Email delivery:</strong> sign-in and invitation emails.</li>
          <li><strong>Messaging platforms</strong> a Customer chooses to use, such as Slack, Meta (WhatsApp) and Microsoft (Teams).</li>
        </ul>
        <p>
          We may also disclose data where the law requires it. We will tell the Customer about a request for its data
          unless the law prohibits us.
        </p>
      </section>

      <section>
        <h2>6. Where data is stored</h2>
        <p>
          Customer data and account data are stored in {LEGAL.hosting}. Some providers above, including AI model
          providers, may process data in other countries. Where data leaves Hong Kong, we take reasonable steps,
          including contractual protections, so that it is protected to a standard comparable to the PDPO.
        </p>
      </section>

      <section>
        <h2>7. How long we keep it</h2>
        <ul>
          <li>Account data: while your account is active, and for up to 90 days after it is closed.</li>
          <li>Customer data: while the Customer&apos;s subscription is active. After it ends we delete it within 90 days, unless the Customer asks for earlier deletion or the law requires us to keep it.</li>
          <li>Billing records: as long as Hong Kong tax and accounting law requires (generally seven years).</li>
          <li>Server logs: up to 90 days.</li>
        </ul>
      </section>

      <section>
        <h2>8. Security</h2>
        <p>
          Each company&apos;s data is kept separate at the database level, so one Customer cannot see another&apos;s data.
          Data is encrypted in transit and at rest, keys and credentials are held in an encrypted vault, and access by
          our staff is limited to what is needed to run and support the Service. No system is perfectly secure; if a
          breach affects your data, we will notify the affected Customer and, where appropriate, the Privacy
          Commissioner for Personal Data, without undue delay.
        </p>
      </section>

      <section>
        <h2>9. Cookies</h2>
        <p>
          We use only the cookies needed to keep you signed in and to protect the Service. We do not use advertising or
          cross-site tracking cookies.
        </p>
      </section>

      <section>
        <h2>10. Your rights</h2>
        <p>
          Under the PDPO you may ask for a copy of the personal data we hold about you and ask us to correct it. You can
          also ask us to delete your account. Write to <a href={`mailto:${LEGAL.contactEmail}`}>{LEGAL.contactEmail}</a>.
          We will reply within 40 days and may charge a fee permitted by the PDPO for a copy of the data. For data in a
          Customer&apos;s workspace, we will pass your request to that Customer.
        </p>
      </section>

      <section>
        <h2>11. Children</h2>
        <p>The Service is for businesses and is not intended for anyone under 18.</p>
      </section>

      <section>
        <h2>12. Changes</h2>
        <p>
          We will post any changes on this page and update the date at the top. For significant changes we will notify
          workspace owners by email before they take effect.
        </p>
      </section>

      <section>
        <h2>13. Contact</h2>
        <p>
          {LEGAL.entity}, {LEGAL.address}. Privacy questions:{" "}
          <a href={`mailto:${LEGAL.contactEmail}`}>{LEGAL.contactEmail}</a>. See also our{" "}
          <Link href="/terms">Terms of Service</Link>.
        </p>
      </section>
    </LegalPage>
  );
}
