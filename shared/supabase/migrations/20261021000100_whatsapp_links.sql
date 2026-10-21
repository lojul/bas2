-- WhatsApp numbers linked to members (one number per member per workspace). Genie answers on
-- WhatsApp only for linked numbers. A member proves the number by sending "LINK <code>" from it to
-- the workspace's WhatsApp number; only the code's SHA-256 is stored, and it expires in 10 minutes.

create table public.whatsapp_links (
  tenant_id uuid not null,
  user_id uuid not null,
  phone text check (phone ~ '^\+[0-9]{6,15}$'),
  code_hash text,
  code_expires_at timestamptz,
  linked_at timestamptz,
  created_at timestamptz not null default now(),
  primary key (tenant_id, user_id),
  -- Leaving or being removed from the workspace removes the link.
  foreign key (tenant_id, user_id) references public.tenant_members (tenant_id, user_id) on delete cascade
);

create unique index whatsapp_links_phone on public.whatsapp_links (tenant_id, phone) where phone is not null;

alter table public.whatsapp_links enable row level security;

-- Members see their own link; owners/admins see the workspace's. Rows are written only by the
-- server (service role) after its own checks.
create policy whatsapp_links_select on public.whatsapp_links for select to authenticated
  using (user_id = (select auth.uid()) or (select private.has_role(tenant_id, '{owner,admin}')));

grant select on public.whatsapp_links to authenticated;
grant all on public.whatsapp_links to service_role;
