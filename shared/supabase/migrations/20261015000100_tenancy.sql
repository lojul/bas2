-- BAS 2.0 / Genie — tenants, members, roles, invitations.
-- Every tenant-owned row carries tenant_id; row-level security checks membership
-- through the helper functions in the `private` schema (not exposed by the Data API).

create extension if not exists vector with schema extensions;
create extension if not exists pg_trgm with schema extensions;

create schema if not exists private;
revoke all on schema private from public, anon;
grant usage on schema private to authenticated, service_role;

create type public.member_role as enum ('owner', 'admin', 'member', 'viewer');

-- ---------------------------------------------------------------------------
-- updated_at helper
-- ---------------------------------------------------------------------------
create function private.set_updated_at() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  return new;
end $$;

-- ---------------------------------------------------------------------------
-- tenants
-- ---------------------------------------------------------------------------
create table public.tenants (
  id                 uuid primary key default gen_random_uuid(),
  slug               text not null unique check (slug ~ '^[a-z0-9][a-z0-9-]{1,48}[a-z0-9]$'),
  name               text not null check (length(name) between 1 and 200),
  plan               text not null default 'starter'
                       check (plan in ('trial', 'starter', 'business', 'enterprise')),
  document_addon     boolean not null default false,
  status             text not null default 'active'
                       check (status in ('active', 'suspended', 'cancelled')),
  stripe_customer_id text unique,
  settings           jsonb not null default '{}'::jsonb,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);
create trigger tenants_updated_at before update on public.tenants
  for each row execute function private.set_updated_at();

-- ---------------------------------------------------------------------------
-- tenant_members (user <-> tenant, with role)
-- ---------------------------------------------------------------------------
create table public.tenant_members (
  tenant_id  uuid not null references public.tenants (id) on delete cascade,
  user_id    uuid not null references auth.users (id) on delete cascade,
  role       public.member_role not null default 'member',
  created_at timestamptz not null default now(),
  primary key (tenant_id, user_id)
);
create index tenant_members_user_idx on public.tenant_members (user_id);

-- ---------------------------------------------------------------------------
-- invitations (portal sends a link containing the raw token; only its hash is stored)
-- ---------------------------------------------------------------------------
create table public.invitations (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references public.tenants (id) on delete cascade,
  email       text not null check (email = lower(email) and position('@' in email) > 1),
  role        public.member_role not null default 'member' check (role <> 'owner'),
  token_hash  text not null unique,
  invited_by  uuid references auth.users (id) on delete set null,
  expires_at  timestamptz not null default now() + interval '7 days',
  accepted_at timestamptz,
  created_at  timestamptz not null default now()
);
create index invitations_tenant_idx on public.invitations (tenant_id);

-- ---------------------------------------------------------------------------
-- Membership helpers. SECURITY DEFINER so policies on tenant_members do not recurse.
-- ---------------------------------------------------------------------------
create function private.is_member(p_tenant_id uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.tenant_members m
    where m.tenant_id = p_tenant_id and m.user_id = (select auth.uid())
  );
$$;

create function private.has_role(p_tenant_id uuid, p_roles public.member_role[]) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.tenant_members m
    where m.tenant_id = p_tenant_id and m.user_id = (select auth.uid())
      and m.role = any (p_roles)
  );
$$;

create function private.my_tenant_ids() returns setof uuid
language sql stable security definer set search_path = '' as $$
  select m.tenant_id from public.tenant_members m where m.user_id = (select auth.uid());
$$;

revoke all on function private.is_member(uuid), private.has_role(uuid, public.member_role[]),
  private.my_tenant_ids() from public, anon;
grant execute on function private.is_member(uuid), private.has_role(uuid, public.member_role[]),
  private.my_tenant_ids() to authenticated, service_role;

-- A tenant must always keep at least one owner.
create function private.keep_one_owner() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if old.role = 'owner'
     and (tg_op = 'DELETE' or new.role <> 'owner' or new.tenant_id <> old.tenant_id)
     and exists (select 1 from public.tenants t where t.id = old.tenant_id)
     and not exists (
       select 1 from public.tenant_members m
       where m.tenant_id = old.tenant_id and m.role = 'owner' and m.user_id <> old.user_id
     ) then
    raise exception 'a tenant must keep at least one owner';
  end if;
  return coalesce(new, old);
end $$;
create trigger tenant_members_keep_owner before update or delete on public.tenant_members
  for each row execute function private.keep_one_owner();

-- ---------------------------------------------------------------------------
-- RPCs used by the portal
-- ---------------------------------------------------------------------------

-- Create a tenant and make the caller its owner.
create function public.create_tenant(p_name text, p_slug text) returns public.tenants
language plpgsql security definer set search_path = '' as $$
declare
  v_uid uuid := (select auth.uid());
  v_tenant public.tenants;
begin
  if v_uid is null then
    raise exception 'not signed in' using errcode = '42501';
  end if;
  insert into public.tenants (name, slug) values (p_name, p_slug) returning * into v_tenant;
  insert into public.tenant_members (tenant_id, user_id, role) values (v_tenant.id, v_uid, 'owner');
  return v_tenant;
end $$;

-- Accept an invitation: the raw token must hash to a pending invite for the caller's email.
create function public.accept_invitation(p_token text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_uid uuid := (select auth.uid());
  v_email text := lower((select auth.jwt()) ->> 'email');
  v_inv public.invitations;
begin
  if v_uid is null then
    raise exception 'not signed in' using errcode = '42501';
  end if;
  select * into v_inv from public.invitations i
  where i.token_hash = encode(extensions.digest(p_token, 'sha256'), 'hex')
    and i.accepted_at is null and i.expires_at > now()
  for update;
  if not found or v_inv.email <> v_email then
    raise exception 'invitation not found, expired, or for another email' using errcode = '42501';
  end if;
  insert into public.tenant_members (tenant_id, user_id, role)
  values (v_inv.tenant_id, v_uid, v_inv.role)
  on conflict (tenant_id, user_id) do nothing;
  update public.invitations set accepted_at = now() where id = v_inv.id;
  return v_inv.tenant_id;
end $$;

revoke all on function public.create_tenant(text, text), public.accept_invitation(text) from public, anon;
grant execute on function public.create_tenant(text, text), public.accept_invitation(text)
  to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Row-level security
-- ---------------------------------------------------------------------------
alter table public.tenants        enable row level security;
alter table public.tenant_members enable row level security;
alter table public.invitations    enable row level security;

-- tenants: members read; owners/admins update. Creation via create_tenant(); deletion by service role.
create policy tenants_select on public.tenants for select to authenticated
  using ((select private.is_member(id)));
create policy tenants_update on public.tenants for update to authenticated
  using ((select private.has_role(id, '{owner,admin}')))
  with check ((select private.has_role(id, '{owner,admin}')));

-- tenant_members: members see their colleagues. Owners manage everyone; admins manage
-- non-owners only. Anyone may remove themselves (the owner trigger still applies).
create policy members_select on public.tenant_members for select to authenticated
  using ((select private.is_member(tenant_id)));
create policy members_insert on public.tenant_members for insert to authenticated
  with check (
    (select private.has_role(tenant_id, '{owner}'))
    or ((select private.has_role(tenant_id, '{admin}')) and role <> 'owner')
  );
create policy members_update on public.tenant_members for update to authenticated
  using (
    (select private.has_role(tenant_id, '{owner}'))
    or ((select private.has_role(tenant_id, '{admin}')) and role <> 'owner')
  )
  with check (
    (select private.has_role(tenant_id, '{owner}'))
    or ((select private.has_role(tenant_id, '{admin}')) and role <> 'owner')
  );
create policy members_delete on public.tenant_members for delete to authenticated
  using (
    user_id = (select auth.uid())
    or (select private.has_role(tenant_id, '{owner}'))
    or ((select private.has_role(tenant_id, '{admin}')) and role <> 'owner')
  );

-- invitations: owners/admins only.
create policy invitations_all on public.invitations for all to authenticated
  using ((select private.has_role(tenant_id, '{owner,admin}')))
  with check ((select private.has_role(tenant_id, '{owner,admin}')));

-- ---------------------------------------------------------------------------
-- Grants (explicit, so behaviour does not depend on project defaults)
-- ---------------------------------------------------------------------------
revoke all on public.tenants, public.tenant_members, public.invitations from anon;
grant select, update on public.tenants to authenticated;
grant select, insert, update, delete on public.tenant_members, public.invitations to authenticated;
grant all on public.tenants, public.tenant_members, public.invitations to service_role;
