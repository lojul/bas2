-- BAS 2.0 / Genie — API keys and the read tools behind the Genie MCP server (/api/mcp).
--
-- An outside agent sends a workspace API key; each mcp_* function resolves the key to its
-- tenant and only ever reads that tenant's rows. The functions are SECURITY DEFINER and
-- callable with the public (publishable) key, so the MCP server needs no service-role secret:
-- the database itself enforces the tenant boundary. Only the SHA-256 of a key is stored.

-- ---------------------------------------------------------------------------
-- api_keys
-- ---------------------------------------------------------------------------
create table public.api_keys (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references public.tenants (id) on delete cascade,
  name         text not null check (length(name) between 1 and 100),
  prefix       text not null,                 -- first characters, shown in the portal
  key_hash     text not null unique,          -- sha256 hex of the full key
  scopes       text[] not null default '{read}',
  created_by   uuid references auth.users (id) on delete set null,
  created_at   timestamptz not null default now(),
  last_used_at timestamptz,
  revoked_at   timestamptz
);
create index api_keys_tenant_idx on public.api_keys (tenant_id);
create index api_keys_created_by_idx on public.api_keys (created_by) where created_by is not null;

alter table public.api_keys enable row level security;
create policy api_keys_select on public.api_keys for select to authenticated
  using ((select private.has_role(tenant_id, '{owner,admin}')));
create policy api_keys_insert on public.api_keys for insert to authenticated
  with check ((select private.has_role(tenant_id, '{owner,admin}')) and created_by = (select auth.uid()));
create policy api_keys_update on public.api_keys for update to authenticated
  using ((select private.has_role(tenant_id, '{owner,admin}')))
  with check ((select private.has_role(tenant_id, '{owner,admin}')));
create policy api_keys_delete on public.api_keys for delete to authenticated
  using ((select private.has_role(tenant_id, '{owner,admin}')));

revoke all on public.api_keys from anon;
grant select, insert, update, delete on public.api_keys to authenticated;
grant all on public.api_keys to service_role;

-- MCP tool calls are metered too.
alter table public.usage_events drop constraint usage_events_metric_check;
alter table public.usage_events add constraint usage_events_metric_check check (metric in
  ('message', 'ocr_page', 'input_token', 'output_token', 'embedding_token', 'synced_record', 'tool_call'));

-- ---------------------------------------------------------------------------
-- Key check: returns the tenant for a valid, unrevoked key on an active tenant, and meters
-- the call. Raises 'invalid api key' (SQLSTATE 28000) otherwise.
-- ---------------------------------------------------------------------------
create function private.mcp_tenant(p_key text, p_tool text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_key_id uuid;
  v_tenant uuid;
begin
  if p_key is null or p_key !~ '^gnk_[A-Za-z0-9_-]{20,100}$' then
    raise exception 'invalid api key' using errcode = '28000';
  end if;
  select k.id, k.tenant_id into v_key_id, v_tenant
  from public.api_keys k
  join public.tenants t on t.id = k.tenant_id and t.status = 'active'
  where k.key_hash = encode(extensions.digest(p_key, 'sha256'), 'hex')
    and k.revoked_at is null;
  if v_tenant is null then
    raise exception 'invalid api key' using errcode = '28000';
  end if;
  update public.api_keys set last_used_at = now()
  where id = v_key_id and (last_used_at is null or last_used_at < now() - interval '1 minute');
  insert into public.usage_events (tenant_id, metric, quantity, channel, metadata)
  values (v_tenant, 'tool_call', 1, 'mcp', jsonb_build_object('tool', p_tool, 'api_key_id', v_key_id));
  return v_tenant;
end $$;

-- ILIKE pattern for a literal search term.
create function private.like_pattern(p_text text) returns text
language sql immutable set search_path = '' as $$
  select '%' || replace(replace(replace(p_text, '\', '\\'), '%', '\%'), '_', '\_') || '%';
$$;

revoke all on function private.mcp_tenant(text, text), private.like_pattern(text) from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- Tools
-- ---------------------------------------------------------------------------

-- What this workspace contains: name, plan, connected sources, record types and counts.
create function public.mcp_workspace(p_key text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_tenant uuid := private.mcp_tenant(p_key, 'workspace_info');
begin
  return (
    select jsonb_build_object(
      'name', t.name,
      'plan', t.plan,
      'sources', coalesce((
        select jsonb_agg(jsonb_build_object('name', s.name, 'kind', s.kind, 'status', s.status,
                                            'last_synced_at', s.last_synced_at) order by s.name)
        from public.sources s where s.tenant_id = t.id), '[]'::jsonb),
      'record_types', coalesce((
        select jsonb_agg(jsonb_build_object('object_type', x.object_type, 'count', x.n) order by x.n desc)
        from (select r.object_type, count(*) as n from public.records r
              where r.tenant_id = t.id and r.deleted_at is null group by r.object_type) x), '[]'::jsonb),
      'documents', (select count(*) from public.documents d where d.tenant_id = t.id and d.status = 'ready')
    )
    from public.tenants t where t.id = v_tenant
  );
end $$;

-- Keyword search over synced records (any type, or one type). Matches the full-text index,
-- title, body and field values; works for Chinese through substring matching.
create function public.mcp_search_records(p_key text, p_query text, p_object_type text default null,
                                          p_limit int default 10) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_tenant uuid := private.mcp_tenant(p_key, 'search_records');
  v_q text := nullif(btrim(coalesce(p_query, '')), '');
  v_like text := private.like_pattern(coalesce(v_q, ''));
  v_ts tsquery := case when v_q is null then null else websearch_to_tsquery('simple', v_q) end;
begin
  return coalesce((
    select jsonb_agg(row_to_json(x)::jsonb)
    from (
      select r.id, r.object_type, r.title, left(r.body, 300) as snippet, s.name as source,
             r.source_updated_at as updated_at
      from public.records r
      join public.sources s on s.id = r.source_id
      where r.tenant_id = v_tenant
        and r.deleted_at is null
        and (p_object_type is null or r.object_type = p_object_type)
        and (v_q is null or r.fts @@ v_ts or r.title ilike v_like or r.body ilike v_like
             or r.data::text ilike v_like)
      order by case when v_q is null then 0 else ts_rank(r.fts, v_ts) end desc,
               case when v_q is null then 0 else extensions.similarity(coalesce(r.title, ''), v_q) end desc,
               r.synced_at desc
      limit least(greatest(coalesce(p_limit, 10), 1), 50)
    ) x), '[]'::jsonb);
end $$;

-- One record with all its fields.
create function public.mcp_get_record(p_key text, p_id uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_tenant uuid := private.mcp_tenant(p_key, 'get_record');
begin
  return (
    select jsonb_build_object('id', r.id, 'object_type', r.object_type, 'external_id', r.external_id,
                              'title', r.title, 'body', r.body, 'fields', r.data, 'source', s.name,
                              'source_kind', s.kind, 'updated_at', r.source_updated_at)
    from public.records r join public.sources s on s.id = r.source_id
    where r.id = p_id and r.tenant_id = v_tenant and r.deleted_at is null
  );
end $$;

-- People and companies by name, email or phone (phone compared on digits only).
create function public.mcp_find_contact(p_key text, p_query text, p_limit int default 10) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_tenant uuid := private.mcp_tenant(p_key, 'find_contact');
  v_q text := btrim(coalesce(p_query, ''));
  v_like text := private.like_pattern(v_q);
  v_digits text := regexp_replace(v_q, '\D', '', 'g');
begin
  if length(v_q) < 2 then
    raise exception 'query too short' using errcode = '22023';
  end if;
  return coalesce((
    select jsonb_agg(row_to_json(x)::jsonb)
    from (
      select r.id, r.object_type, r.title as name,
             coalesce(r.data->>'email', r.data->>'email_from') as email,
             coalesce(r.data->>'phone', r.data->>'mobile') as phone,
             coalesce(r.data->>'company', r.data->>'company_name', r.data->>'parent_name') as company,
             s.name as source
      from public.records r join public.sources s on s.id = r.source_id
      where r.tenant_id = v_tenant and r.deleted_at is null
        and r.object_type in ('contact', 'customer', 'person', 'company', 'res.partner', 'supplier', 'vendor')
        and (r.title ilike v_like
             or coalesce(r.data->>'email', '') ilike v_like
             or (length(v_digits) >= 4 and (
                   regexp_replace(coalesce(r.data->>'phone', ''), '\D', '', 'g') like '%' || v_digits || '%'
                or regexp_replace(coalesce(r.data->>'mobile', ''), '\D', '', 'g') like '%' || v_digits || '%')))
      order by extensions.similarity(coalesce(r.title, ''), v_q) desc, r.title
      limit least(greatest(coalesce(p_limit, 10), 1), 50)
    ) x), '[]'::jsonb);
end $$;

-- Passages from documents and long text (the embedded chunks), by keyword for now.
-- Semantic search (match_chunks) joins once the embedding job exists.
create function public.mcp_search_knowledge(p_key text, p_query text, p_limit int default 8) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_tenant uuid := private.mcp_tenant(p_key, 'search_knowledge');
  v_q text := btrim(coalesce(p_query, ''));
  v_like text := private.like_pattern(v_q);
  v_ts tsquery := websearch_to_tsquery('simple', v_q);
begin
  if length(v_q) < 2 then
    raise exception 'query too short' using errcode = '22023';
  end if;
  return coalesce((
    select jsonb_agg(row_to_json(x)::jsonb)
    from (
      select c.id as chunk_id, left(c.content, 800) as passage,
             coalesce(d.file_name, r.title) as from_title,
             case when c.document_id is not null then 'document' else 'record' end as from_kind,
             coalesce(c.document_id, c.record_id) as from_id
      from public.chunks c
      left join public.documents d on d.id = c.document_id
      left join public.records r on r.id = c.record_id
      where c.tenant_id = v_tenant
        and (to_tsvector('simple', c.content) @@ v_ts or c.content ilike v_like)
      order by ts_rank(to_tsvector('simple', c.content), v_ts) desc, c.created_at desc
      limit least(greatest(coalesce(p_limit, 8), 1), 30)
    ) x), '[]'::jsonb);
end $$;

revoke all on function public.mcp_workspace(text), public.mcp_search_records(text, text, text, int),
  public.mcp_get_record(text, uuid), public.mcp_find_contact(text, text, int),
  public.mcp_search_knowledge(text, text, int) from public;
grant execute on function public.mcp_workspace(text), public.mcp_search_records(text, text, text, int),
  public.mcp_get_record(text, uuid), public.mcp_find_contact(text, text, int),
  public.mcp_search_knowledge(text, text, int) to anon, authenticated, service_role;
