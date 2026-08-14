-- ════════════════════════════════════════════════
-- Migration 0022 — RLS de `contactos`, `oportunidades` e `imoveis`
-- (projecto UNIFICADO, zphasvfopnbzwnaidsnw)
-- ════════════════════════════════════════════════
-- Estas três tabelas são criadas pelo pipeline externo do eGO, não pelas
-- migrations — foi por isso que escaparam à `0003`, que só cobriu as `agente_*`.
-- Tinham RLS ligado, mas com políticas que o anulavam:
--
--   contactos      "service role full access"  ALL    to public  using (true)
--   imoveis        "service role full access"  ALL    to public  using (true)
--   imoveis        "imoveis_public_read"       SELECT to anon    using (true)
--   oportunidades  "allow_read_all"            SELECT to public  using (true)
--
-- `public` é o role-pai de `anon` e `authenticated`. Com `using (true)` e
-- `for all`, as duas primeiras davam SELECT/INSERT/UPDATE/DELETE a qualquer
-- anónimo — incluindo a `contactos`, que tem telefone, data de nascimento,
-- nacionalidade e as colunas `rgpd_*` de pessoas reais.
--
-- O nome "service role full access" é o erro de raiz: o `service_role`
-- **bypassa RLS por definição** e nunca precisa de política. A política não
-- concedia nada ao backend e concedia tudo ao resto do mundo.
--
-- Seguro de aplicar: o backend (`get_supabase()`) e o scraper usam ambos
-- `service_role`; o painel nunca fala com o PostgREST directamente — o
-- frontend só usa o Supabase para `auth.*`, tudo o resto passa pela API.

-- ── 1. Remover as políticas permissivas ──────────────────────────────────
drop policy if exists "service role full access" on contactos;
drop policy if exists "service role full access" on imoveis;
drop policy if exists "allow_read_all"           on oportunidades;

-- `imoveis_public_read` dava a todas as 60 colunas de todos os imóveis a
-- anónimos — inclui `proprietario`, `angariador` e `comissao_*`. Nada no
-- repositório a usa (procurado: só o frontend tem chave `anon`, e aponta para
-- o projecto de autenticação). Se um site externo depender dela, ver o bloco
-- no fim deste ficheiro em vez de a remover.
drop policy if exists "imoveis_public_read" on imoveis;

-- ── 2. Repor o acesso autenticado, como no resto do projecto ─────────────
-- Mesmo padrão da `0003`: o painel entra com JWT, o `anon` fica de fora.
drop policy if exists "auth_full_access" on contactos;
create policy "auth_full_access" on contactos
  for all to authenticated using (true) with check (true);

drop policy if exists "auth_full_access" on oportunidades;
create policy "auth_full_access" on oportunidades
  for all to authenticated using (true) with check (true);

drop policy if exists "auth_full_access" on imoveis;
create policy "auth_full_access" on imoveis
  for all to authenticated using (true) with check (true);

-- ── VERIFICAÇÃO (correr depois; esperado: zero linhas) ───────────────────
-- Políticas abertas a anon/public cuja condição não depende de quem entrou:
--
-- select tablename, policyname, cmd, roles::text, qual::text, with_check::text
-- from pg_policies
-- where schemaname = 'public'
--   and (roles::text like '%anon%' or roles::text like '%public%')
--   and coalesce(qual::text, '')       !~ 'auth\.uid|auth\.jwt|auth\.role'
--   and coalesce(with_check::text, '') !~ 'auth\.uid|auth\.jwt|auth\.role';
--
-- E as tabelas sem RLS de todo, que a query acima não consegue ver porque não
-- têm políticas nenhumas para listar:
--
-- select tablename from pg_tables
-- where schemaname = 'public' and not rowsecurity order by tablename;

-- ── SE um site externo ler imóveis com a chave `anon` deste projecto ─────
-- Não remover a política acima às cegas — repor esta em vez dela. Restringe às
-- linhas publicadas (`publicado` é GENERATED, migration 0008), o que já é
-- melhor do que `using (true)`:
--
-- create policy "imoveis_public_read" on imoveis
--   for select to anon using (publicado = true);
--
-- Continua a expor todas as colunas dessas linhas: o RLS filtra linhas, não
-- colunas. Esconder `proprietario` e as comissões exige uma view com a
-- allowlist de colunas e dar o SELECT à view, não à tabela.
