import Link from "next/link";
import { BRAND } from "@/lib/brand";

export function SiteFooter() {
  return (
    <footer className="mt-auto flex flex-wrap items-center gap-x-4 gap-y-1 pt-16 text-xs text-genie-muted">
      <span>© {BRAND.company}</span>
      <Link href="/privacy" className="hover:text-genie-ink">Privacy</Link>
      <Link href="/terms" className="hover:text-genie-ink">Terms</Link>
    </footer>
  );
}
