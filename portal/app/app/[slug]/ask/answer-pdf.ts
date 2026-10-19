// "Download PDF" under a Genie answer (user 2026-10-19): lays that one answer out as a clean page
// (workspace name, title, date, the answer with its tables and source links, a check-before-sending
// line) and opens the browser's print dialog, where "Save as PDF" makes the file. Made in the
// browser from the answer on screen, so nothing new is stored in Genie.

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

const CSS = `
@page { margin: 16mm 14mm; }
* { box-sizing: border-box; }
body { font: 11pt/1.5 -apple-system, "Segoe UI", "Helvetica Neue", Arial, "PingFang HK", "Microsoft JhengHei", sans-serif; color: #1f1f1f; margin: 0; }
header { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 2px solid #1f1f1f; padding-bottom: 6px; margin-bottom: 14px; }
header .org { font-weight: 600; font-size: 12pt; }
header .date { color: #666; font-size: 9.5pt; }
h1 { font-size: 16pt; margin: 0 0 12px; }
p { margin: 6px 0; }
ul, ol { margin: 6px 0; padding-left: 20px; }
table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 9.5pt; page-break-inside: auto; }
tr { page-break-inside: avoid; }
th { background: #f3f3f3; text-align: left; font-weight: 600; }
th, td { border: 1px solid #d6d6d6; padding: 5px 7px; vertical-align: top; }
a { color: #1a56db; text-decoration: underline; }
code { font-family: ui-monospace, Menlo, monospace; font-size: 0.9em; }
footer { margin-top: 18px; padding-top: 8px; border-top: 1px solid #d6d6d6; color: #666; font-size: 8.5pt; }
`;

export function downloadAnswerPdf(opts: { answerEl: HTMLElement; title: string; workspaceName: string }) {
  const body = opts.answerEl.cloneNode(true) as HTMLElement;
  // Drop closing lines meant for the staff member ("Want me to prepare a lead…", "Would you like…?").
  for (let i = 0; i < 2; i++) {
    const last = body.lastElementChild;
    const text = last?.textContent?.trim() ?? "";
    if (last?.tagName !== "P" || body.children.length < 2) break;
    if (!/\?$/.test(text) && !/^(want me|would you|shall i|should i|do you want|let me know|if you('d| would) like|tell me)/i.test(text)) break;
    last.remove();
  }
  // Genie's own heading ("**Shortlist: …**" on a line of its own, within the first lines) is the page
  // title; the lead-in to the staff member above it ("Here is the shortlist…") is left out.
  const isHeading = (el: Element) =>
    el.tagName === "P" &&
    el.children.length === 1 &&
    el.firstElementChild!.tagName === "STRONG" &&
    el.textContent!.trim() === el.firstElementChild!.textContent!.trim() &&
    el.textContent!.trim().length <= 120;
  const headingEl = [...body.children].slice(0, 3).find(isHeading) ?? null;
  const heading = headingEl?.textContent?.trim() ?? null;
  if (headingEl) {
    while (body.firstElementChild && body.firstElementChild !== headingEl) body.firstElementChild.remove();
    headingEl.remove();
  }
  // Tables scroll on screen; in print they take the full width.
  body.querySelectorAll("div").forEach((d) => d.removeAttribute("class"));
  body.querySelectorAll("[class]").forEach((el) => el.removeAttribute("class"));

  const date = new Date().toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  const fromQuestion = opts.title.replace(/@genie\b/gi, "").replace(/["“”]/g, "").replace(/\s+/g, " ").trim();
  const title = (heading ?? fromQuestion.charAt(0).toUpperCase() + fromQuestion.slice(1)) || "Report";
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>${esc(title)}</title><style>${CSS}</style></head><body>
<header><span class="org">${esc(opts.workspaceName)}</span><span class="date">${esc(date)}</span></header>
<h1>${esc(title)}</h1>
${body.innerHTML}
<footer>Prepared on ${esc(date)} from ${esc(opts.workspaceName)}'s records and documents. Please check availability, rents and terms before relying on them.</footer>
</body></html>`;

  // A hidden frame keeps the print to this one page and avoids pop-up blockers.
  const frame = document.createElement("iframe");
  frame.setAttribute("aria-hidden", "true");
  frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;";
  document.body.appendChild(frame);
  const doc = frame.contentDocument!;
  doc.open();
  doc.write(html);
  doc.close();
  const win = frame.contentWindow!;
  const done = () => setTimeout(() => frame.remove(), 1000);
  win.addEventListener("afterprint", done);
  // Wait a moment for fonts and layout before opening the print dialog.
  setTimeout(() => {
    win.focus();
    win.print();
  }, 250);
  setTimeout(() => frame.isConnected && frame.remove(), 5 * 60 * 1000);
}
