-- BAS 2.0 / Genie — member directory for the portal.
-- auth.users is not readable by signed-in users, so the members page reads names and emails
-- through this function, which only answers for tenants the caller belongs to.

create function public.list_tenant_members(p_tenant_id uuid)
returns table (user_id uuid, email text, role public.member_role, joined_at timestamptz)
language sql stable security definer set search_path = '' as $$
  select m.user_id, u.email::text, m.role, m.created_at
  from public.tenant_members m
  join auth.users u on u.id = m.user_id
  where m.tenant_id = p_tenant_id
    and private.is_member(p_tenant_id)
  order by m.role, u.email;
$$;

revoke all on function public.list_tenant_members(uuid) from public, anon;
grant execute on function public.list_tenant_members(uuid) to authenticated, service_role;
