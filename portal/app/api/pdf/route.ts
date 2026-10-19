import { NextResponse } from "next/server";
import { htmlToPdf } from "@/lib/pdf/render";
import { getUser } from "@/lib/supabase/server";
import { getWorkspace } from "@/lib/workspaces";

// Download PDF under a Genie answer (Ask): the browser sends the page it laid out, this returns it as
// a .pdf file. Members of the workspace only; nothing is stored.
export const runtime = "nodejs";
export const maxDuration = 60;

const MAX_HTML = 1_000_000;

export async function POST(request: Request) {
  const { user } = await getUser();
  if (!user) return NextResponse.json({ error: "Sign in first." }, { status: 401 });
  const body = (await request.json().catch(() => null)) as { slug?: unknown; html?: unknown } | null;
  const slug = typeof body?.slug === "string" ? body.slug : "";
  const html = typeof body?.html === "string" ? body.html : "";
  if (!html || html.length > MAX_HTML) return NextResponse.json({ error: "Nothing to turn into a PDF." }, { status: 400 });
  if (!(await getWorkspace(user.id, slug))) return NextResponse.json({ error: "Workspace not found." }, { status: 403 });

  try {
    const pdf = await htmlToPdf(html);
    return new NextResponse(Buffer.from(pdf), { headers: { "Content-Type": "application/pdf", "Cache-Control": "no-store" } });
  } catch (e) {
    console.error("pdf failed", e);
    return NextResponse.json({ error: "Could not make the PDF." }, { status: 500 });
  }
}
