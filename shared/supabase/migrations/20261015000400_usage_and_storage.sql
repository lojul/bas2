-- BAS 2.0 / Genie — usage metering (for Stripe Billing) and the private documents bucket.

-- ---------------------------------------------------------------------------
-- usage_events: one row per metered event, written by server code (service role).
-- Aggregated per month for Stripe meter reporting and the portal's usage page.
-- ---------------------------------------------------------------------------
create table public.usage_events (
  id          bigint generated always as identity primary key,
  tenant_id   uuid not null references public.tenants (id) on delete cascade,
  metric      text not null check (metric in
                ('message', 'ocr_page', 'input_token', 'output_token',
                 'embedding_token', 'synced_record')),
  quantity    bigint not null check (quantity >= 0),
  model       text,                 -- for token metrics
  key_source  text check (key_source in ('platform', 'byok')),  -- whose AI key paid
  channel     text,                 -- web, slack, whatsapp, teams, mcp, sync, ...
  user_id     uuid references auth.users (id) on delete set null,
  metadata    jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default now(),
  reported_at timestamptz           -- set once sent to Stripe
);
create index usage_events_tenant_metric_idx on public.usage_events (tenant_id, metric, occurred_at);
create index usage_events_unreported_idx on public.usage_events (occurred_at) where reported_at is null;

alter table public.usage_events enable row level security;
create policy usage_events_select on public.usage_events for select to authenticated
  using ((select private.has_role(tenant_id, '{owner,admin}')));

create view public.usage_monthly with (security_invoker = true) as
  select tenant_id, metric, key_source,
         date_trunc('month', occurred_at) as month,
         sum(quantity)::bigint as quantity
  from public.usage_events
  group by tenant_id, metric, key_source, date_trunc('month', occurred_at);

revoke all on public.usage_events, public.usage_monthly from anon;
grant select on public.usage_events, public.usage_monthly to authenticated;
grant all on public.usage_events to service_role;
grant select on public.usage_monthly to service_role;

-- ---------------------------------------------------------------------------
-- Storage: private bucket 'documents', objects stored as <tenant_id>/<anything>
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit)
values ('documents', 'documents', false, 52428800)   -- 50 MB per file
on conflict (id) do nothing;

create policy documents_bucket_select on storage.objects for select to authenticated
  using (
    bucket_id = 'documents'
    and (storage.foldername(name))[1] in (select t::text from private.my_tenant_ids() t)
  );
create policy documents_bucket_insert on storage.objects for insert to authenticated
  with check (
    bucket_id = 'documents'
    and exists (
      select 1 from public.tenant_members m
      where m.user_id = (select auth.uid())
        and m.tenant_id::text = (storage.foldername(name))[1]
        and m.role in ('owner', 'admin', 'member')
    )
  );
create policy documents_bucket_delete on storage.objects for delete to authenticated
  using (
    bucket_id = 'documents'
    and exists (
      select 1 from public.tenant_members m
      where m.user_id = (select auth.uid())
        and m.tenant_id::text = (storage.foldername(name))[1]
        and m.role in ('owner', 'admin')
    )
  );
