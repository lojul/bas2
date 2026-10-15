-- BAS 2.0 / Genie — one implementation of each agent tool, shared by two entry points:
--   * public.mcp_*        — outside agents, authenticated by a workspace API key (MCP server)
--   * public.agent_tool() — Genie's own agent in the portal, acting as a signed-in member
-- The tool bodies move to private.tool_* (tenant id in, jsonb out); the entry points only
-- decide which tenant the caller may read and meter the call.

-- ---------------------------------------------------------------------------
-- Tool implementations (not exposed through the Data API)
-- ---------------------------------------------------------------------------
create function private.tool_workspace(p_tenant uuid) returns jsonb
language sql stable security definer set search_path = '' as $$
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
  from public.tenants t where t.id = p_tenant;
$$;

create function private.tool_search_records(p_tenant uuid, p_query text, p_object_type text, p_limit int)
returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare
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
      where r.tenant_id = p_tenant
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

create function private.tool_get_record(p_tenant uuid, p_id uuid) returns jsonb
language sql stable security definer set search_path = '' as $$
  select jsonb_build_object('id', r.id, 'object_type', r.object_type, 'external_id', r.external_id,
                            'title', r.title, 'body', r.body, 'fields', r.data, 'source', s.name,
                            'source_kind', s.kind, 'updated_at', r.source_updated_at)
  from public.records r join public.sources s on s.id = r.source_id
  where r.id = p_id and r.tenant_id = p_tenant and r.deleted_at is null;
$$;

create function private.tool_find_contact(p_tenant uuid, p_query text, p_limit int) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare
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
      where r.tenant_id = p_tenant and r.deleted_at is null
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

create function private.tool_search_knowledge(p_tenant uuid, p_query text, p_limit int) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare
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
      where c.tenant_id = p_tenant
        and (to_tsvector('simple', c.content) @@ v_ts or c.content ilike v_like)
      order by ts_rank(to_tsvector('simple', c.content), v_ts) desc, c.created_at desc
      limit least(greatest(coalesce(p_limit, 8), 1), 30)
    ) x), '[]'::jsonb);
end $$;

-- Dispatcher used by both entry points. Unknown tools raise 22023.
create function private.run_tool(p_tenant uuid, p_tool text, p_args jsonb) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  a jsonb := coalesce(p_args, '{}'::jsonb);
begin
  case p_tool
    when 'workspace_info' then
      return private.tool_workspace(p_tenant);
    when 'search_records' then
      return private.tool_search_records(p_tenant, a->>'query', a->>'object_type',
                                         coalesce((a->>'limit')::int, 10));
    when 'get_record' then
      return private.tool_get_record(p_tenant, (a->>'id')::uuid);
    when 'find_contact' then
      return private.tool_find_contact(p_tenant, a->>'query', coalesce((a->>'limit')::int, 10));
    when 'search_knowledge' then
      return private.tool_search_knowledge(p_tenant, a->>'query', coalesce((a->>'limit')::int, 8));
    else
      raise exception 'unknown tool %', p_tool using errcode = '22023';
  end case;
end $$;

revoke all on function private.tool_workspace(uuid), private.tool_search_records(uuid, text, text, int),
  private.tool_get_record(uuid, uuid), private.tool_find_contact(uuid, text, int),
  private.tool_search_knowledge(uuid, text, int), private.run_tool(uuid, text, jsonb)
  from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- MCP entry points now delegate (same signatures and behaviour as 20261015000700)
-- ---------------------------------------------------------------------------
create or replace function public.mcp_workspace(p_key text) returns jsonb
language sql security definer set search_path = '' as $$
  select private.tool_workspace(private.mcp_tenant(p_key, 'workspace_info'));
$$;

create or replace function public.mcp_search_records(p_key text, p_query text, p_object_type text default null,
                                                     p_limit int default 10) returns jsonb
language sql security definer set search_path = '' as $$
  select private.tool_search_records(private.mcp_tenant(p_key, 'search_records'), p_query, p_object_type, p_limit);
$$;

create or replace function public.mcp_get_record(p_key text, p_id uuid) returns jsonb
language sql security definer set search_path = '' as $$
  select private.tool_get_record(private.mcp_tenant(p_key, 'get_record'), p_id);
$$;

create or replace function public.mcp_find_contact(p_key text, p_query text, p_limit int default 10) returns jsonb
language sql security definer set search_path = '' as $$
  select private.tool_find_contact(private.mcp_tenant(p_key, 'find_contact'), p_query, p_limit);
$$;

create or replace function public.mcp_search_knowledge(p_key text, p_query text, p_limit int default 8) returns jsonb
language sql security definer set search_path = '' as $$
  select private.tool_search_knowledge(private.mcp_tenant(p_key, 'search_knowledge'), p_query, p_limit);
$$;

-- ---------------------------------------------------------------------------
-- Portal entry point: the signed-in user must be a member of the workspace.
-- ---------------------------------------------------------------------------
create function public.agent_tool(p_tenant_id uuid, p_tool text, p_args jsonb default '{}'::jsonb)
returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  if not private.is_member(p_tenant_id) then
    raise exception 'not a member of this workspace' using errcode = '42501';
  end if;
  insert into public.usage_events (tenant_id, metric, quantity, channel, user_id, metadata)
  values (p_tenant_id, 'tool_call', 1, 'web', (select auth.uid()), jsonb_build_object('tool', p_tool));
  return private.run_tool(p_tenant_id, p_tool, p_args);
end $$;

revoke all on function public.agent_tool(uuid, text, jsonb) from public, anon;
grant execute on function public.agent_tool(uuid, text, jsonb) to authenticated, service_role;
