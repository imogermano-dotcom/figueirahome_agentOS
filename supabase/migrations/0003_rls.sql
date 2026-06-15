-- ════════════════════════════════════════════════
-- FIGUEIRA HOME — Row Level Security (Fase 4c)
-- Backend usa service_role key → bypass automático.
-- authenticated → acesso total.
-- anon → bloqueado por defeito.
-- ════════════════════════════════════════════════

-- ENABLE RLS
alter table agente_clientes  enable row level security;
alter table agente_imoveis   enable row level security;
alter table agente_leads     enable row level security;
alter table agente_chamadas  enable row level security;
alter table agente_conversas enable row level security;
alter table agente_config    enable row level security;

-- POLÍTICAS: utilizadores autenticados têm acesso total
create policy "auth_full_access" on agente_clientes
  for all to authenticated using (true) with check (true);

create policy "auth_full_access" on agente_imoveis
  for all to authenticated using (true) with check (true);

create policy "auth_full_access" on agente_leads
  for all to authenticated using (true) with check (true);

create policy "auth_full_access" on agente_chamadas
  for all to authenticated using (true) with check (true);

create policy "auth_full_access" on agente_conversas
  for all to authenticated using (true) with check (true);

create policy "auth_full_access" on agente_config
  for all to authenticated using (true) with check (true);

-- VERIFICAÇÃO (executar após aplicar):
-- select relname, relrowsecurity
-- from pg_class
-- where relname like 'agente_%'
-- order by relname;
-- Esperado: relrowsecurity = true em todas as 6 tabelas.
