import { redirect } from "next/navigation";

// A workspace opens on Ask (decided 2026-10-16: the Overview page repeated the sidebar).
export default async function WorkspaceHome({ params }: PageProps<"/app/[slug]">) {
  const { slug } = await params;
  redirect(`/app/${slug}/ask`);
}
