-- BAS 2.0 / Genie — fixes from the Supabase performance advisor.

-- Covering indexes for the same-tenant composite foreign keys (used by cascades and joins).
drop index if exists public.chunks_record_idx;
drop index if exists public.chunks_document_idx;
create index chunks_record_idx on public.chunks (record_id, tenant_id) where record_id is not null;
create index chunks_document_idx on public.chunks (document_id, tenant_id) where document_id is not null;
create index records_source_idx on public.records (source_id, tenant_id);
create index documents_source_idx on public.documents (source_id, tenant_id) where source_id is not null;
create index sources_secret_idx on public.sources (secret_id, tenant_id) where secret_id is not null;

-- Foreign keys to auth.users (ON DELETE SET NULL when a user is deleted).
create index documents_uploaded_by_idx on public.documents (uploaded_by) where uploaded_by is not null;
create index invitations_invited_by_idx on public.invitations (invited_by) where invited_by is not null;
create index sources_created_by_idx on public.sources (created_by) where created_by is not null;
create index tenant_secrets_created_by_idx on public.tenant_secrets (created_by) where created_by is not null;
create index usage_events_user_idx on public.usage_events (user_id) where user_id is not null;

-- sources: one policy per action instead of a FOR ALL policy overlapping the SELECT policy.
drop policy sources_write on public.sources;
create policy sources_insert on public.sources for insert to authenticated
  with check ((select private.has_role(tenant_id, '{owner,admin}')));
create policy sources_update on public.sources for update to authenticated
  using ((select private.has_role(tenant_id, '{owner,admin}')))
  with check ((select private.has_role(tenant_id, '{owner,admin}')));
create policy sources_delete on public.sources for delete to authenticated
  using ((select private.has_role(tenant_id, '{owner,admin}')));
