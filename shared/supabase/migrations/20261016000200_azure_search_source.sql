-- A customer's own Azure AI Search index as a live, read-only data source (decided 2026-10-16:
-- Genie reads it at question time with a query key; nothing is copied into Genie).
alter table public.sources drop constraint sources_kind_check;
alter table public.sources add constraint sources_kind_check check (kind in
  ('sql', 'csv', 'odoo_json2', 'odoo_mcp', 'odoo_xmlrpc', 'documents', 'manual', 'azure_search'));
