import Link from "next/link";
import { Sparkles } from "lucide-react";
import { BRAND } from "@/lib/brand";

export function Logo({ href = "/" }: { href?: string }) {
  return (
    <Link href={href} className="inline-flex items-center gap-2 text-lg font-semibold text-genie-ink">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-genie-green-deep text-white">
        <Sparkles size={16} />
      </span>
      {BRAND.name}
    </Link>
  );
}
