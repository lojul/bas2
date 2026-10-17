-- Saved chats for Ask (user decision 2026-10-17): an exception to "nothing stored" — conversations are
-- kept so members can share them, but deleted automatically 90 days after the last message.
-- Business records themselves are still never copied; only what was said in a chat.
--   team    chats: every member of the workspace can read and post (also members who join later).
--   private chats: only the person who started it.

create table public.chats (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references public.tenants (id) on delete cascade,
  title           text not null check (length(title) between 1 and 120),
  visibility      text not null default 'private' check (visibility in ('team', 'private')),
  created_by      uuid references auth.users (id) on delete set null,
  created_at      timestamptz not null default now(),
  last_message_at timestamptz not null default now()
);
create index chats_tenant_idx on public.chats (tenant_id, last_message_at desc);

create table public.chat_messages (
  id           uuid primary key default gen_random_uuid(),
  chat_id      uuid not null references public.chats (id) on delete cascade,
  tenant_id    uuid not null references public.tenants (id) on delete cascade,
  role         text not null check (role in ('user', 'assistant')),
  author_id    uuid references auth.users (id) on delete set null,
  author_email text,                       -- shown next to the message
  content      text not null check (length(content) between 1 and 20000),
  meta         jsonb not null default '{}'::jsonb,   -- model, key source, tools used
  created_at   timestamptz not null default now()
);
create index chat_messages_chat_idx on public.chat_messages (chat_id, created_at);

-- Who can see a chat: members of its workspace for team chats; its creator for private ones.
create function private.can_see_chat(p_chat_id uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.chats c
    where c.id = p_chat_id
      and private.is_member(c.tenant_id)
      and (c.visibility = 'team' or c.created_by = (select auth.uid()))
  );
$$;
revoke all on function private.can_see_chat(uuid) from public, anon;
grant execute on function private.can_see_chat(uuid) to authenticated, service_role;

alter table public.chats enable row level security;
alter table public.chat_messages enable row level security;

create policy chats_select on public.chats for select to authenticated
  using ((select private.is_member(tenant_id)) and (visibility = 'team' or created_by = (select auth.uid())));
create policy chats_insert on public.chats for insert to authenticated
  with check ((select private.is_member(tenant_id)) and created_by = (select auth.uid()));
-- The creator can rename or delete; owners/admins can delete any chat in their workspace.
create policy chats_update on public.chats for update to authenticated
  using (created_by = (select auth.uid()) and (select private.is_member(tenant_id)))
  with check (created_by = (select auth.uid()));
create policy chats_delete on public.chats for delete to authenticated
  using ((select private.is_member(tenant_id)) and (created_by = (select auth.uid()) or (select private.has_role(tenant_id, '{owner,admin}'))));

create policy chat_messages_select on public.chat_messages for select to authenticated
  using ((select private.can_see_chat(chat_id)));
-- People post their own messages; Genie's answers are written by the server (service role).
create policy chat_messages_insert on public.chat_messages for insert to authenticated
  with check (role = 'user' and author_id = (select auth.uid()) and (select private.can_see_chat(chat_id)));

grant select, insert, update, delete on public.chats to authenticated;
grant select, insert on public.chat_messages to authenticated;

-- A new message moves its chat to the top of the list.
create function private.touch_chat() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  update public.chats set last_message_at = new.created_at where id = new.chat_id;
  return new;
end $$;
create trigger chat_messages_touch after insert on public.chat_messages
  for each row execute function private.touch_chat();

-- Live updates for everyone looking at a chat (Realtime respects the policies above).
alter publication supabase_realtime add table public.chat_messages;

-- Retention: delete chats 90 days after their last message, every night at 03:00 HKT.
create extension if not exists pg_cron;
select cron.schedule('genie-chat-retention', '0 19 * * *',
  $$delete from public.chats where last_message_at < now() - interval '90 days'$$);
