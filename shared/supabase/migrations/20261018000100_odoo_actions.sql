-- Changes in Odoo from Ask (user decision 2026-10-17): Genie proposes a change, a person confirms it,
-- then the server writes it to Odoo with the workspace's dedicated "Genie" Odoo user key.
-- One row per proposed change. `draft` holds the proposed values only until the change is decided
-- (or 24 hours); after that only who / what / when / which Odoo record is kept (no copy of the data).

create table public.odoo_actions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references public.tenants on delete cascade,
  chat_id uuid references public.chats on delete set null,
  requested_by uuid references auth.users on delete set null,
  requested_email text,
  action text not null check (action in ('create_lead', 'create_contact', 'add_note', 'schedule_follow_up', 'update_record')),
  model text not null,
  record_id bigint,
  draft jsonb,
  status text not null default 'proposed' check (status in ('proposed', 'done', 'cancelled', 'failed', 'expired')),
  error text,
  decided_by uuid references auth.users on delete set null,
  decided_email text,
  created_at timestamptz not null default now(),
  decided_at timestamptz
);

create index odoo_actions_tenant_created on public.odoo_actions (tenant_id, created_at desc);

alter table public.odoo_actions enable row level security;

-- Owners/admins see the workspace's log; everyone sees the changes they asked for.
-- Rows are written only by the server (service role) after its own checks.
create policy odoo_actions_select on public.odoo_actions for select to authenticated
  using (requested_by = auth.uid() or private.has_role(tenant_id, '{owner,admin}'));

grant select on public.odoo_actions to authenticated;
grant all on public.odoo_actions to service_role;

-- Hourly: drafts older than 24 hours expire; decided drafts lose their values; log kept 1 year.
select cron.schedule(
  'genie-odoo-actions-cleanup',
  '17 * * * *',
  $$
  update public.odoo_actions set status = 'expired', draft = null
    where status = 'proposed' and created_at < now() - interval '24 hours';
  update public.odoo_actions set draft = null
    where draft is not null and status <> 'proposed';
  delete from public.odoo_actions where created_at < now() - interval '1 year';
  $$
);
