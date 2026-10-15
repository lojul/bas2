-- BAS 2.0 / Genie — tenant isolation test.
--
-- Run as the `postgres` role (SQL Editor, psql, or the Supabase MCP execute_sql tool).
-- The whole test is one DO block that ALWAYS ends by raising an exception, so every row
-- it creates (users, tenants, Vault secrets, storage objects) is rolled back.
--   Pass:  ERROR:  ALL CHECKS PASSED (n checks)
--   Fail:  ERROR:  FAIL: <what went wrong>

do $test$
declare
  ua uuid := gen_random_uuid();   -- owner of tenant A
  um uuid := gen_random_uuid();   -- member of tenant A
  uv uuid := gen_random_uuid();   -- viewer of tenant A
  ub uuid := gen_random_uuid();   -- owner of tenant B
  ta uuid := gen_random_uuid();
  tb uuid := gen_random_uuid();
  sa uuid; sb uuid;               -- sources
  secret_b uuid;
  rec uuid;
  emb extensions.vector(1536) := array_fill(0.1, array[1536])::extensions.vector;
  n int;
  v text;
  ok boolean;
  state text;
  checks int := 0;
begin
  -- -------------------------------------------------------------------------
  -- Setup (as postgres, bypassing RLS)
  -- -------------------------------------------------------------------------
  insert into auth.users (id, email, aud, role)
  values (ua, 'owner-a@test.invalid', 'authenticated', 'authenticated'),
         (um, 'member-a@test.invalid', 'authenticated', 'authenticated'),
         (uv, 'viewer-a@test.invalid', 'authenticated', 'authenticated'),
         (ub, 'owner-b@test.invalid', 'authenticated', 'authenticated');

  insert into public.tenants (id, slug, name) values
    (ta, 'test-tenant-a', 'Test A'), (tb, 'test-tenant-b', 'Test B');
  insert into public.tenant_members (tenant_id, user_id, role) values
    (ta, ua, 'owner'), (ta, um, 'member'), (ta, uv, 'viewer'), (tb, ub, 'owner');

  insert into public.sources (tenant_id, kind, name) values (ta, 'sql', 'A db') returning id into sa;
  insert into public.sources (tenant_id, kind, name) values (tb, 'sql', 'B db') returning id into sb;

  insert into public.records (tenant_id, source_id, object_type, external_id, title, body)
  values (ta, sa, 'listing', '1', 'A listing one', 'harbour view'),
         (ta, sa, 'listing', '2', 'A listing two', 'garden');
  insert into public.records (tenant_id, source_id, object_type, external_id, title, body)
  values (tb, sb, 'listing', '1', 'B secret listing', 'harbour view') returning id into rec;

  insert into public.chunks (tenant_id, record_id, content, embedding)
  select r.tenant_id, r.id, r.body, emb from public.records r;

  insert into public.documents (tenant_id, storage_path, file_name)
  values (ta, ta || '/a.pdf', 'a.pdf'), (tb, tb || '/b.pdf', 'b.pdf');

  insert into public.usage_events (tenant_id, metric, quantity) values (ta, 'message', 1), (tb, 'message', 5);

  -- Secrets are stored through the RPC, as each tenant's owner.
  perform set_config('role', 'authenticated', true);
  perform set_config('request.jwt.claims',
    json_build_object('sub', ua, 'role', 'authenticated', 'email', 'owner-a@test.invalid')::text, true);
  perform public.set_tenant_secret(ta, 'openrouter', 'ai_key', 'openrouter', 'sk-test-AAAA-1111');
  perform set_config('request.jwt.claims',
    json_build_object('sub', ub, 'role', 'authenticated', 'email', 'owner-b@test.invalid')::text, true);
  secret_b := public.set_tenant_secret(tb, 'openrouter', 'ai_key', 'openrouter', 'sk-test-BBBB-2222');

  -- -------------------------------------------------------------------------
  -- As the OWNER of tenant A
  -- -------------------------------------------------------------------------
  perform set_config('request.jwt.claims',
    json_build_object('sub', ua, 'role', 'authenticated', 'email', 'owner-a@test.invalid')::text, true);

  select count(*) into n from public.tenants;
  if n <> 1 then raise exception 'FAIL: owner A sees % tenants (expected 1)', n; end if;
  checks := checks + 1;

  select count(*) into n from public.records where tenant_id = tb;
  if n <> 0 then raise exception 'FAIL: owner A sees % of tenant B''s records', n; end if;
  select count(*) into n from public.records;
  if n <> 2 then raise exception 'FAIL: owner A sees % records (expected 2)', n; end if;
  checks := checks + 1;

  select count(*) into n from public.records where title ilike '%secret%';
  if n <> 0 then raise exception 'FAIL: text search leaks tenant B''s record to owner A'; end if;
  checks := checks + 1;

  select count(*) into n from public.chunks where tenant_id = tb;
  if n <> 0 then raise exception 'FAIL: owner A sees tenant B''s chunks'; end if;
  checks := checks + 1;

  select count(*) into n from public.match_chunks(tb, emb, 10);
  if n <> 0 then raise exception 'FAIL: match_chunks returns % of tenant B''s chunks to owner A', n; end if;
  select count(*) into n from public.match_chunks(ta, emb, 10);
  if n <> 2 then raise exception 'FAIL: match_chunks returns % own chunks (expected 2)', n; end if;
  checks := checks + 1;

  select count(*) into n from public.documents;
  if n <> 1 then raise exception 'FAIL: owner A sees % documents (expected 1)', n; end if;
  checks := checks + 1;

  select count(*) into n from public.usage_events;
  if n <> 1 then raise exception 'FAIL: owner A sees % usage events (expected 1)', n; end if;
  select coalesce(sum(quantity), 0) into n from public.usage_monthly;
  if n <> 1 then raise exception 'FAIL: usage_monthly shows % for owner A (expected 1)', n; end if;
  checks := checks + 1;

  select count(*) into n from public.tenant_secrets;
  if n <> 1 then raise exception 'FAIL: owner A sees % secret rows (expected 1)', n; end if;
  select hint into v from public.tenant_secrets;
  if v <> '1111' then raise exception 'FAIL: secret hint is % (expected last 4 only)', v; end if;
  checks := checks + 1;

  ok := false;
  begin
    perform public.get_tenant_secret(ta, 'openrouter');
  exception when insufficient_privilege then ok := true;
  end;
  if not ok then raise exception 'FAIL: owner A can call get_tenant_secret'; end if;
  checks := checks + 1;

  ok := false;
  begin
    perform count(*) from vault.decrypted_secrets;
  exception when insufficient_privilege then ok := true;
  end;
  if not ok then raise exception 'FAIL: owner A can read vault.decrypted_secrets'; end if;
  checks := checks + 1;

  ok := false;
  begin
    perform public.set_tenant_secret(tb, 'openrouter', 'ai_key', 'openrouter', 'sk-hijack');
  exception when insufficient_privilege then ok := true;
  end;
  if not ok then raise exception 'FAIL: owner A can overwrite tenant B''s secret'; end if;
  checks := checks + 1;

  ok := false;
  begin
    insert into public.sources (tenant_id, kind, name) values (tb, 'sql', 'planted');
  exception when insufficient_privilege then ok := true;
  end;
  if not ok then raise exception 'FAIL: owner A can create a source in tenant B'; end if;
  checks := checks + 1;

  update public.tenants set name = 'hijacked' where id = tb;
  get diagnostics n = row_count;
  if n <> 0 then raise exception 'FAIL: owner A renamed tenant B'; end if;
  checks := checks + 1;

  ok := false;
  begin
    insert into public.tenant_members (tenant_id, user_id, role) values (tb, ua, 'owner');
  exception when insufficient_privilege then ok := true;
  end;
  if not ok then raise exception 'FAIL: owner A can add themselves to tenant B'; end if;
  checks := checks + 1;

  ok := false;
  begin
    insert into public.records (tenant_id, source_id, object_type, external_id)
    values (ta, sa, 'listing', 'x');
  exception when insufficient_privilege then ok := true;
  end;
  if not ok then raise exception 'FAIL: a signed-in user can write records directly'; end if;
  checks := checks + 1;

  -- Composite keys: tenant A's connector must not be able to use tenant B's credentials.
  ok := false;
  begin
    insert into public.sources (tenant_id, kind, name, secret_id) values (ta, 'sql', 'borrow', secret_b);
  exception when foreign_key_violation then ok := true;
  end;
  if not ok then raise exception 'FAIL: tenant A source can reference tenant B''s secret'; end if;
  checks := checks + 1;

  ok := false;
  begin
    insert into public.documents (tenant_id, storage_path, file_name, uploaded_by, source_id)
    values (ta, ta || '/x.pdf', 'x.pdf', ua, sb);
  exception when foreign_key_violation then ok := true;
  end;
  if not ok then raise exception 'FAIL: tenant A document can reference tenant B''s source'; end if;
  checks := checks + 1;

  -- Storage: uploads only under the caller's own tenant folder.
  ok := false;
  begin
    insert into storage.objects (bucket_id, name, owner_id) values ('documents', tb || '/planted.pdf', ua::text);
  exception when insufficient_privilege then ok := true;
  end;
  if not ok then raise exception 'FAIL: owner A can upload into tenant B''s storage folder'; end if;
  insert into storage.objects (bucket_id, name, owner_id) values ('documents', ta || '/own.pdf', ua::text);
  checks := checks + 1;

  -- -------------------------------------------------------------------------
  -- As a MEMBER of tenant A
  -- -------------------------------------------------------------------------
  perform set_config('request.jwt.claims',
    json_build_object('sub', um, 'role', 'authenticated', 'email', 'member-a@test.invalid')::text, true);

  select count(*) into n from public.tenant_secrets;
  if n <> 0 then raise exception 'FAIL: a member sees % secret rows (expected 0)', n; end if;
  select count(*) into n from public.usage_events;
  if n <> 0 then raise exception 'FAIL: a member sees usage events'; end if;
  checks := checks + 1;

  ok := false;
  begin
    perform public.set_tenant_secret(ta, 'openrouter', 'ai_key', 'openrouter', 'sk-member');
  exception when insufficient_privilege then ok := true;
  end;
  if not ok then raise exception 'FAIL: a member can change a secret'; end if;
  checks := checks + 1;

  ok := false;
  begin
    update public.tenant_members set role = 'admin' where tenant_id = ta and user_id = um;
    get diagnostics n = row_count;
    if n = 0 then ok := true; end if;
  exception when insufficient_privilege then ok := true;
  end;
  if not ok then raise exception 'FAIL: a member can promote themselves'; end if;
  checks := checks + 1;

  insert into public.documents (tenant_id, storage_path, file_name, uploaded_by)
  values (ta, ta || '/member.pdf', 'member.pdf', um);
  checks := checks + 1;

  -- -------------------------------------------------------------------------
  -- As a VIEWER of tenant A
  -- -------------------------------------------------------------------------
  perform set_config('request.jwt.claims',
    json_build_object('sub', uv, 'role', 'authenticated', 'email', 'viewer-a@test.invalid')::text, true);

  ok := false;
  begin
    insert into public.documents (tenant_id, storage_path, file_name, uploaded_by)
    values (ta, ta || '/viewer.pdf', 'viewer.pdf', uv);
  exception when insufficient_privilege then ok := true;
  end;
  if not ok then raise exception 'FAIL: a viewer can upload a document'; end if;
  select count(*) into n from public.records;
  if n <> 2 then raise exception 'FAIL: a viewer sees % records (expected 2)', n; end if;
  checks := checks + 1;

  -- -------------------------------------------------------------------------
  -- As ANON (not signed in)
  -- -------------------------------------------------------------------------
  perform set_config('role', 'anon', true);
  perform set_config('request.jwt.claims', json_build_object('role', 'anon')::text, true);

  ok := false;
  begin
    select count(*) into n from public.tenants;
    if n = 0 then ok := true; end if;
  exception when insufficient_privilege then ok := true;
  end;
  if not ok then raise exception 'FAIL: anon can read tenants'; end if;

  ok := false;
  begin
    perform public.create_tenant('x', 'anon-tenant');
  exception when insufficient_privilege then ok := true;
  end;
  if not ok then raise exception 'FAIL: anon can create a tenant'; end if;
  checks := checks + 1;

  -- -------------------------------------------------------------------------
  -- As the SERVICE ROLE (server code)
  -- -------------------------------------------------------------------------
  perform set_config('role', 'service_role', true);
  perform set_config('request.jwt.claims', json_build_object('role', 'service_role')::text, true);

  v := public.get_tenant_secret(ta, 'openrouter');
  if v is distinct from 'sk-test-AAAA-1111' then raise exception 'FAIL: service role cannot read tenant A''s secret'; end if;
  v := public.get_tenant_secret(tb, 'openrouter');
  if v is distinct from 'sk-test-BBBB-2222' then raise exception 'FAIL: tenant B''s secret was changed'; end if;
  checks := checks + 1;

  -- -------------------------------------------------------------------------
  -- Ownership and cleanup rules (as postgres)
  -- -------------------------------------------------------------------------
  perform set_config('role', 'postgres', true);

  ok := false;
  begin
    delete from public.tenant_members where tenant_id = tb and user_id = ub;
  exception when raise_exception then ok := true;
  end;
  if not ok then raise exception 'FAIL: the last owner of a tenant can be removed'; end if;
  checks := checks + 1;

  select count(*) into n from vault.secrets where name like 'tenant:' || tb || ':%';
  if n <> 1 then raise exception 'FAIL: expected 1 Vault entry for tenant B, found %', n; end if;
  delete from public.tenants where id = tb;
  select count(*) into n from vault.secrets where name like 'tenant:' || tb || ':%';
  if n <> 0 then raise exception 'FAIL: deleting a tenant left % Vault entries behind', n; end if;
  checks := checks + 1;

  raise exception 'ALL CHECKS PASSED (% checks)', checks;
end
$test$;
