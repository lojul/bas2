import { redirect } from "next/navigation";

// Moved into Settings; kept so old links keep working.
export default async function Page({ params }: PageProps<"/app/[slug]/sources">) {
  const { slug } = await params;
  redirect(`/app/${slug}/settings#data-sources`);
}
