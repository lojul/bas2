-- Live data sources (decided 2026-10-16): Genie stores no copy of customer business data. Tools
-- read the customer's system (Odoo) at question time. The portal server does that with the
-- service role, so it needs to turn an MCP API key into its workspace without the old
-- records-based tool functions.

-- Workspace for a valid, unrevoked key on an active workspace, or null. Updates last_used_at.
-- Metering is done by the caller (one tool_call per tool run).
create function public.mcp_key_tenant(p_key text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_key_id uuid;
  v_tenant uuid;
begin
  if p_key is null or p_key !~ '^gnk_[A-Za-z0-9_-]{20,100}$' then
    return null;
  end if;
  select k.id, k.tenant_id into v_key_id, v_tenant
  from public.api_keys k
  join public.tenants t on t.id = k.tenant_id and t.status = 'active'
  where k.key_hash = encode(extensions.digest(p_key, 'sha256'), 'hex')
    and k.revoked_at is null;
  if v_tenant is not null then
    update public.api_keys set last_used_at = now()
    where id = v_key_id and (last_used_at is null or last_used_at < now() - interval '1 minute');
  end if;
  return v_tenant;
end $$;

revoke all on function public.mcp_key_tenant(text) from public, anon, authenticated;
grant execute on function public.mcp_key_tenant(text) to service_role;
