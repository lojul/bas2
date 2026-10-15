-- BAS 2.0 / Genie — per-tenant secrets (AI keys, connector credentials) in Supabase Vault.
-- Tables only ever hold the Vault secret id and a masked hint, never the secret itself.
-- Owners/admins may store, replace or delete a secret; only the service role (server code)
-- can read the decrypted value, through public.get_tenant_secret().

create table public.tenant_secrets (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references public.tenants (id) on delete cascade,
  name            text not null check (name ~ '^[a-z0-9_.-]{1,64}$'),
  kind            text not null check (kind in ('ai_key', 'connector', 'webhook', 'other')),
  provider        text,           -- e.g. anthropic, xai, openrouter, azure_openai, odoo, postgres
  hint            text,           -- last 4 characters, for display only
  vault_secret_id uuid not null unique,
  created_by      uuid references auth.users (id) on delete set null,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique (tenant_id, name),
  unique (id, tenant_id)
);
create trigger tenant_secrets_updated_at before update on public.tenant_secrets
  for each row execute function private.set_updated_at();

alter table public.tenant_secrets enable row level security;
create policy tenant_secrets_select on public.tenant_secrets for select to authenticated
  using ((select private.has_role(tenant_id, '{owner,admin}')));
-- No insert/update/delete policies: writes go through the functions below.

revoke all on public.tenant_secrets from anon;
grant select on public.tenant_secrets to authenticated;
grant all on public.tenant_secrets to service_role;

-- Vault secret names are globally unique, so they are namespaced by tenant.
create function private.vault_name(p_tenant_id uuid, p_name text) returns text
language sql immutable set search_path = '' as $$
  select 'tenant:' || p_tenant_id::text || ':' || p_name;
$$;

-- Store or replace a secret. Caller must be owner/admin of the tenant (or the service role).
create function public.set_tenant_secret(
  p_tenant_id uuid, p_name text, p_kind text, p_provider text, p_secret text
) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_row public.tenant_secrets;
  v_vault_id uuid;
begin
  -- Fail closed: a missing JWT role is treated as unprivileged.
  if coalesce((select auth.role()), '') <> 'service_role'
     and not private.has_role(p_tenant_id, '{owner,admin}') then
    raise exception 'only tenant owners and admins can manage secrets' using errcode = '42501';
  end if;
  if p_secret is null or length(p_secret) = 0 then
    raise exception 'secret is empty';
  end if;

  select * into v_row from public.tenant_secrets s
  where s.tenant_id = p_tenant_id and s.name = p_name for update;

  if found then
    perform vault.update_secret(v_row.vault_secret_id, p_secret);
    update public.tenant_secrets
       set kind = p_kind, provider = p_provider, hint = right(p_secret, 4)
     where id = v_row.id;
    return v_row.id;
  end if;

  v_vault_id := vault.create_secret(p_secret, private.vault_name(p_tenant_id, p_name),
                                    'Genie tenant secret');
  insert into public.tenant_secrets (tenant_id, name, kind, provider, hint, vault_secret_id, created_by)
  values (p_tenant_id, p_name, p_kind, p_provider, right(p_secret, 4), v_vault_id, (select auth.uid()))
  returning id into v_row.id;
  return v_row.id;
end $$;

create function public.delete_tenant_secret(p_tenant_id uuid, p_name text) returns void
language plpgsql security definer set search_path = '' as $$
begin
  -- Fail closed: a missing JWT role is treated as unprivileged.
  if coalesce((select auth.role()), '') <> 'service_role'
     and not private.has_role(p_tenant_id, '{owner,admin}') then
    raise exception 'only tenant owners and admins can manage secrets' using errcode = '42501';
  end if;
  -- The tenant_secrets_drop_vault trigger removes the Vault entry.
  delete from public.tenant_secrets s where s.tenant_id = p_tenant_id and s.name = p_name;
end $$;

-- Read a decrypted secret. Service role only (server-side code: sync workers, model gateway).
create function public.get_tenant_secret(p_tenant_id uuid, p_name text) returns text
language sql stable security definer set search_path = '' as $$
  select d.decrypted_secret
  from public.tenant_secrets s
  join vault.decrypted_secrets d on d.id = s.vault_secret_id
  where s.tenant_id = p_tenant_id and s.name = p_name;
$$;

-- Remove the Vault entry when a tenant (and so its tenant_secrets rows) is deleted.
create function private.drop_vault_secret() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  delete from vault.secrets where id = old.vault_secret_id;
  return old;
end $$;
create trigger tenant_secrets_drop_vault after delete on public.tenant_secrets
  for each row execute function private.drop_vault_secret();

revoke all on function public.set_tenant_secret(uuid, text, text, text, text),
  public.delete_tenant_secret(uuid, text), public.get_tenant_secret(uuid, text),
  private.vault_name(uuid, text), private.drop_vault_secret() from public, anon, authenticated;
grant execute on function public.set_tenant_secret(uuid, text, text, text, text),
  public.delete_tenant_secret(uuid, text) to authenticated, service_role;
grant execute on function public.get_tenant_secret(uuid, text) to service_role;
