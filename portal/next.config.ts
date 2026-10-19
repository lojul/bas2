import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Headless Chrome for Download PDF (lib/pdf): kept out of the bundle so its binary files stay in
  // place, and shipped with the route together with the Chinese fonts.
  serverExternalPackages: ["@sparticuz/chromium", "puppeteer-core"],
  outputFileTracingIncludes: {
    "/api/pdf": ["./node_modules/@sparticuz/chromium/bin/**/*", "./assets/fonts/*.ttf"],
  },
};

export default nextConfig;
