import { copyFile, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import chromium from "@sparticuz/chromium";
import puppeteer from "puppeteer-core";

// HTML → PDF in a headless Chrome inside Genie's own server (user 2026-10-19: a real .pdf file, no
// outside service, no key). The PDF is made and returned; nothing is stored.
// On Vercel the Chrome from @sparticuz/chromium is used; locally, the installed Google Chrome.

const FONTS = ["NotoSansTC.ttf", "NotoSansSC.ttf"];

// The server Chrome only ships Latin fonts. Its font config also reads /tmp/fonts, so the Chinese
// fonts kept in the repo (assets/fonts) are copied there once per server instance.
async function installFonts() {
  const dir = join(tmpdir(), "fonts");
  if (FONTS.every((f) => existsSync(join(dir, f)))) return;
  await mkdir(dir, { recursive: true });
  await Promise.all(FONTS.map((f) => copyFile(join(process.cwd(), "assets", "fonts", f), join(dir, f))));
}

async function launch() {
  if (process.env.VERCEL) {
    await installFonts();
    return puppeteer.launch({
      args: await puppeteer.defaultArgs({ args: chromium.args, headless: "shell" }),
      executablePath: await chromium.executablePath(),
      headless: "shell",
    });
  }
  return puppeteer.launch({
    executablePath: process.env.CHROME_PATH ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    headless: true,
  });
}

export async function htmlToPdf(html: string): Promise<Uint8Array> {
  const browser = await launch();
  try {
    const page = await browser.newPage();
    // The HTML comes from the member's browser: no scripts, and no requests to anywhere
    // (images, frames, fonts by URL), so it can't make the server fetch something.
    await page.setJavaScriptEnabled(false);
    await page.setRequestInterception(true);
    page.on("request", (req) => void req.abort());
    await page.setContent(html, { waitUntil: "load", timeout: 20_000 });
    return await page.pdf({ format: "A4", printBackground: true, preferCSSPageSize: true, timeout: 30_000 });
  } finally {
    await browser.close();
  }
}
