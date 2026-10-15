import { cache } from "react";
import { type Role } from "@/lib/roles";
import { createClient } from "@/lib/supabase/server";

export { type Role, ROLE_LABEL, canManage } from "@/lib/roles";

export type Workspace = {
  id: string;
  slug: string;
  name: string;
  plan: string;
  document_addon: boolean;
  created_at: string;
  role: Role;
};

type MembershipRow = {
  role: Role;
  tenants: Omit<Workspace, "role"> | null;
};

const TENANT_FIELDS = "role, tenants!inner(id, slug, name, plan, document_addon, created_at)";

// Every workspace the signed-in user belongs to. Row-level security limits the rows.
export const listMyWorkspaces = cache(async (userId: string): Promise<Workspace[]> => {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("tenant_members")
    .select(TENANT_FIELDS)
    .eq("user_id", userId)
    .returns<MembershipRow[]>();
  if (error) throw error;
  return (data ?? [])
    .filter((row) => row.tenants)
    .map((row) => ({ ...row.tenants!, role: row.role }))
    .sort((a, b) => a.name.localeCompare(b.name));
});

// One workspace by slug, or null when it does not exist or the user is not a member.
export const getWorkspace = cache(async (userId: string, slug: string): Promise<Workspace | null> => {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("tenant_members")
    .select(TENANT_FIELDS)
    .eq("user_id", userId)
    .eq("tenants.slug", slug)
    .returns<MembershipRow[]>()
    .maybeSingle();
  if (error) throw error;
  if (!data?.tenants) return null;
  return { ...data.tenants, role: data.role };
});
