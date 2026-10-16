import type { Metadata } from "next";
import { HelpCenter } from "./help-center";

export const metadata: Metadata = { title: "Help" };

export default async function HelpPage({ params }: PageProps<"/app/[slug]/help">) {
  const { slug } = await params;
  return <HelpCenter slug={slug} />;
}
