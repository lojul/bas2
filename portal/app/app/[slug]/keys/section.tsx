import { redirect } from "next/navigation";
import { KeyRound, Lock } from "lucide-react";
import { BRAND } from "@/lib/brand";
import { providerLabel } from "@/lib/providers";
import { createClient, getUser } from "@/lib/supabase/server";
import { canManage, getWorkspace } from "@/lib/workspaces";
import { deleteAiKey } from "./actions";
import { KeyForm } from "./key-form";


type SecretRow = { id: string; name: string; provider: string | null; hint: string | null; updated_at: string };

export async function KeysSection({ slug }: { slug: string }) {
  const { user } = await getUser();
  if (!user) redirect("/login");
  const workspace = (await getWorkspace(user.id, slug))!;
  if (!canManage(workspace.role)) {
    return <p className="text-sm text-genie-muted">Only owners and admins can see this page.</p>;
  }

  const supabase = await createClient();
  const { data: keys } = await supabase
    .from("tenant_secrets")
    .select("id, name, provider, hint, updated_at")
    .eq("tenant_id", workspace.id)
    .eq("kind", "ai_key")
    .order("name")
    .returns<SecretRow[]>();

  return (
    <div className="space-y-6">
      <section className="card">
        <h2 className="font-medium">Use your own AI key</h2>
        <p className="mb-4 mt-1 text-sm text-genie-muted">
          Optional. Without one, {BRAND.name}{" "}uses its platform key and the usage counts towards your plan. With your
          own key, the provider bills you directly.
        </p>
        <KeyForm slug={slug} />
        <p className="mt-4 flex items-center gap-1.5 text-xs text-genie-muted">
          <Lock size={12} /> Keys are encrypted in Supabase Vault. Nobody can read them back in the portal — only{" "}
          {BRAND.name}&apos;s servers use them when calling the provider.
        </p>
      </section>

      <section>
        <h2 className="mb-2 font-medium">Saved keys</h2>
        {keys && keys.length > 0 ? (
          <ul className="divide-y divide-genie-border rounded-xl border border-genie-border bg-genie-card">
            {keys.map((k) => (
              <li key={k.id} className="flex items-center justify-between px-5 py-3 text-sm">
                <div className="flex items-center gap-3">
                  <KeyRound size={16} className="text-genie-green" />
                  <div>
                    <div className="font-medium">{providerLabel(k.provider)}</div>
                    <div className="font-mono text-xs text-genie-muted">
                      ••••{k.hint} · updated {new Date(k.updated_at).toLocaleDateString()}
                    </div>
                  </div>
                </div>
                <form action={deleteAiKey}>
                  <input type="hidden" name="slug" value={slug} />
                  <input type="hidden" name="name" value={k.name} />
                  <button type="submit" className="btn-danger">Delete</button>
                </form>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-genie-muted">No keys saved — the platform key is used.</p>
        )}
      </section>
    </div>
  );
}
