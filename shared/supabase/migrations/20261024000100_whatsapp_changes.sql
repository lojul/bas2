-- Changes in Odoo from WhatsApp, with a short conversation memory (user decision 2026-10-24).
-- Genie on WhatsApp now remembers a member's last messages for 30 minutes, so it can ask for a
-- missing detail and act on the reply. A draft change is confirmed by replying YES (NO cancels).

-- Where a change was asked for: shown in the Odoo note ("… (WhatsApp)") and used to find the drafts
-- a YES / NO reply refers to.
alter table public.odoo_actions
  add column channel text not null default 'web' check (channel in ('web', 'whatsapp'));

-- The member's recent WhatsApp messages and Genie's answers. Kept 30 minutes, then deleted.
-- `proposals`: the drafts of changes in Odoo made in that answer (what YES / NO applies to).
create table public.whatsapp_turns (
  id bigint generated always as identity primary key,
  tenant_id uuid not null,
  user_id uuid not null,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  proposals uuid[] not null default '{}',
  created_at timestamptz not null default now(),
  -- Leaving or being removed from the workspace removes them.
  foreign key (tenant_id, user_id) references public.tenant_members (tenant_id, user_id) on delete cascade
);

create index whatsapp_turns_member on public.whatsapp_turns (tenant_id, user_id, created_at desc);

-- Read and written only by the server (service role); no access for signed-in users.
alter table public.whatsapp_turns enable row level security;
grant all on public.whatsapp_turns to service_role;

-- Every 5 minutes: delete messages older than 30 minutes.
select cron.schedule('genie-whatsapp-memory', '*/5 * * * *',
  $$delete from public.whatsapp_turns where created_at < now() - interval '30 minutes'$$);
