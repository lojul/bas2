-- BAS 2.0 / Genie — connected sources, synced records, documents and the vector store.
-- The customer's system stays the system of record: `records` is a read copy written by
-- sync workers (service role). Members can read everything in their tenant.

-- ---------------------------------------------------------------------------
-- sources: one row per connector instance (an SQL database, a CSV upload, an Odoo, ...)
-- ---------------------------------------------------------------------------
create table public.sources (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references public.tenants (id) on delete cascade,
  kind           text not null check (kind in
                   ('sql', 'csv', 'odoo_json2', 'odoo_mcp', 'odoo_xmlrpc', 'documents', 'manual')),
  name           text not null check (length(name) between 1 and 200),
  config         jsonb not null default '{}'::jsonb,   -- non-secret settings and field mapping
  secret_id      uuid,
  status         text not null default 'pending'
                   check (status in ('pending', 'active', 'paused', 'error')),
  last_synced_at timestamptz,
  last_error     text,
  created_by     uuid references auth.users (id) on delete set null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  unique (tenant_id, name),
  unique (id, tenant_id),
  -- Composite keys keep every cross-reference inside the same tenant.
  foreign key (secret_id, tenant_id) references public.tenant_secrets (id, tenant_id)
    on delete set null (secret_id)
);
create trigger sources_updated_at before update on public.sources
  for each row execute function private.set_updated_at();

-- ---------------------------------------------------------------------------
-- records: normalised copy of a source row (a listing, contact, lead, product, ...)
-- ---------------------------------------------------------------------------
create table public.records (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null references public.tenants (id) on delete cascade,
  source_id         uuid not null,
  object_type       text not null,             -- e.g. 'listing', 'contact', 'crm.lead'
  external_id       text not null,             -- id in the customer's system
  title             text,
  body              text,                      -- text used for search and embeddings
  data              jsonb not null default '{}'::jsonb,
  source_updated_at timestamptz,
  synced_at         timestamptz not null default now(),
  deleted_at        timestamptz,               -- soft delete when gone from the source
  fts               tsvector generated always as
                      (to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(body, ''))) stored,
  unique (source_id, object_type, external_id),
  unique (id, tenant_id),
  foreign key (source_id, tenant_id) references public.sources (id, tenant_id) on delete cascade
);
create index records_tenant_type_idx on public.records (tenant_id, object_type) where deleted_at is null;
create index records_fts_idx on public.records using gin (fts);
-- Trigram index: substring search that also works for Chinese building names.
create index records_title_trgm_idx on public.records using gin (title extensions.gin_trgm_ops);
create index records_data_idx on public.records using gin (data jsonb_path_ops);

-- ---------------------------------------------------------------------------
-- documents: uploaded files (bytes live in Storage bucket 'documents' under <tenant_id>/...)
-- ---------------------------------------------------------------------------
create table public.documents (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references public.tenants (id) on delete cascade,
  source_id    uuid,
  storage_path text not null unique,
  file_name    text not null,
  mime_type    text,
  size_bytes   bigint,
  page_count   int,
  status       text not null default 'uploaded'
                 check (status in ('uploaded', 'processing', 'ready', 'failed')),
  doc_type     text,                            -- set by classification
  extracted    jsonb not null default '{}'::jsonb,
  error        text,
  uploaded_by  uuid references auth.users (id) on delete set null,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  check (storage_path like tenant_id::text || '/%'),
  unique (id, tenant_id),
  foreign key (source_id, tenant_id) references public.sources (id, tenant_id)
    on delete set null (source_id)
);
create index documents_tenant_idx on public.documents (tenant_id, created_at desc);
create trigger documents_updated_at before update on public.documents
  for each row execute function private.set_updated_at();

-- ---------------------------------------------------------------------------
-- chunks: embedded text for semantic search, from a record or a document
-- Embedding size 1536 (e.g. OpenAI text-embedding-3-small); the model is stored per row.
-- Changing the dimension later needs a migration and a re-embed.
-- ---------------------------------------------------------------------------
create table public.chunks (
  id              bigint generated always as identity primary key,
  tenant_id       uuid not null references public.tenants (id) on delete cascade,
  record_id       uuid,
  document_id     uuid,
  chunk_index     int not null default 0,
  content         text not null,
  metadata        jsonb not null default '{}'::jsonb,
  embedding       extensions.vector(1536),
  embedding_model text,
  created_at      timestamptz not null default now(),
  check (num_nonnulls(record_id, document_id) = 1),
  foreign key (record_id, tenant_id) references public.records (id, tenant_id) on delete cascade,
  foreign key (document_id, tenant_id) references public.documents (id, tenant_id) on delete cascade
);
create index chunks_tenant_idx on public.chunks (tenant_id);
create index chunks_record_idx on public.chunks (record_id) where record_id is not null;
create index chunks_document_idx on public.chunks (document_id) where document_id is not null;
create index chunks_embedding_idx on public.chunks
  using hnsw (embedding extensions.vector_cosine_ops);

-- Semantic search within one tenant. SECURITY INVOKER, so row-level security still applies:
-- a member asking about another tenant gets nothing back.
create function public.match_chunks(
  p_tenant_id uuid,
  p_query_embedding extensions.vector(1536),
  p_match_count int default 10,
  p_min_similarity float default 0
) returns table (
  id bigint, record_id uuid, document_id uuid, content text, metadata jsonb, similarity float
)
language sql stable security invoker
set search_path = ''
set hnsw.iterative_scan = 'relaxed_order'
as $$
  select c.id, c.record_id, c.document_id, c.content, c.metadata,
         1 - (c.embedding operator(extensions.<=>) p_query_embedding) as similarity
  from public.chunks c
  where c.tenant_id = p_tenant_id
    and c.embedding is not null
    and 1 - (c.embedding operator(extensions.<=>) p_query_embedding) >= p_min_similarity
  order by c.embedding operator(extensions.<=>) p_query_embedding
  limit least(greatest(p_match_count, 1), 100);
$$;
revoke all on function public.match_chunks(uuid, extensions.vector, int, float) from public, anon;
grant execute on function public.match_chunks(uuid, extensions.vector, int, float)
  to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Row-level security
-- ---------------------------------------------------------------------------
alter table public.sources   enable row level security;
alter table public.records   enable row level security;
alter table public.documents enable row level security;
alter table public.chunks    enable row level security;

-- sources: members read; owners/admins manage.
create policy sources_select on public.sources for select to authenticated
  using ((select private.is_member(tenant_id)));
create policy sources_write on public.sources for all to authenticated
  using ((select private.has_role(tenant_id, '{owner,admin}')))
  with check ((select private.has_role(tenant_id, '{owner,admin}')));

-- records and chunks: members read; only the service role writes (sync and embedding workers).
create policy records_select on public.records for select to authenticated
  using (tenant_id in (select private.my_tenant_ids()));
create policy chunks_select on public.chunks for select to authenticated
  using (tenant_id in (select private.my_tenant_ids()));

-- documents: members read; members (not viewers) upload as themselves; owners/admins edit/delete.
create policy documents_select on public.documents for select to authenticated
  using ((select private.is_member(tenant_id)));
create policy documents_insert on public.documents for insert to authenticated
  with check (
    (select private.has_role(tenant_id, '{owner,admin,member}'))
    and uploaded_by = (select auth.uid())
    and status = 'uploaded'
  );
create policy documents_update on public.documents for update to authenticated
  using ((select private.has_role(tenant_id, '{owner,admin}')))
  with check ((select private.has_role(tenant_id, '{owner,admin}')));
create policy documents_delete on public.documents for delete to authenticated
  using ((select private.has_role(tenant_id, '{owner,admin}')));

-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------
revoke all on public.sources, public.records, public.documents, public.chunks from anon;
grant select, insert, update, delete on public.sources, public.documents to authenticated;
grant select on public.records, public.chunks to authenticated;
grant all on public.sources, public.records, public.documents, public.chunks to service_role;
