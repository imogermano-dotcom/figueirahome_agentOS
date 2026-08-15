-- ════════════════════════════════════════════════
-- Migration 0025 — fechar a ESCRITA anónima em `contactos` e `imoveis`
-- (projecto UNIFICADO, zphasvfopnbzwnaidsnw)
-- ════════════════════════════════════════════════
-- Fatia urgente da `0022`, que continua por aplicar à espera de se saber que
-- chave o portal do Miguel usa. Esta corre sem essa resposta porque **não mexe
-- em nenhuma leitura**: um portal que mostra informação só lê.
--
-- O problema: as duas tabelas têm uma política chamada "service role full
-- access" com `roles = {public}`, `for all`, `using (true)`. O nome é o erro de
-- raiz — o `service_role` bypassa RLS por definição e nunca precisa de
-- política. O que a política concede de facto é SELECT **e INSERT/UPDATE/DELETE**
-- a qualquer anónimo, incluindo em `contactos`, que tem telefone, data de
-- nascimento, nacionalidade e colunas `rgpd_*` de pessoas reais.
--
-- Ou seja: hoje, quem tenha a chave `anon` deste projecto pode apagar a base de
-- contactos. É isso que esta migration tira da mesa.
--
-- O que NÃO faz, e fica para a `0022`: retirar a leitura anónima. Isso pode
-- partir o portal e precisa da confirmação do Miguel.

-- ── contactos ────────────────────────────────────────────────────────────
-- A leitura anónima passa a estar numa política explícita e só de SELECT, em
-- vez de vir de arrasto numa `for all`. Comportamento de leitura idêntico.
drop policy if exists "service role full access" on contactos;

drop policy if exists "leitura_publica_legado" on contactos;
create policy "leitura_publica_legado" on contactos
  for select to public using (true);

drop policy if exists "auth_full_access" on contactos;
create policy "auth_full_access" on contactos
  for all to authenticated using (true) with check (true);

-- ── imoveis ──────────────────────────────────────────────────────────────
-- Aqui a leitura anónima já vem de `imoveis_public_read` (SELECT to anon), que
-- se mantém intacta — basta remover a `for all`.
drop policy if exists "service role full access" on imoveis;

drop policy if exists "auth_full_access" on imoveis;
create policy "auth_full_access" on imoveis
  for all to authenticated using (true) with check (true);

-- `oportunidades` não entra: `allow_read_all` já é só SELECT, não há escrita
-- anónima para fechar. Fica para a `0022`.

-- ── VERIFICAÇÃO (esperado: zero linhas) ──────────────────────────────────
-- Escrita anónima ainda possível em alguma tabela:
--
-- select tablename, policyname, cmd, roles::text
-- from pg_policies
-- where schemaname = 'public'
--   and cmd in ('ALL','INSERT','UPDATE','DELETE')
--   and (roles::text like '%anon%' or roles::text like '%public%')
--   and coalesce(qual::text, '') !~ 'auth\.uid|auth\.jwt|auth\.role';
--
-- E confirmar que a leitura não mudou (o portal continua a ler):
-- select tablename, policyname, cmd, roles::text from pg_policies
--  where schemaname='public' and tablename in ('contactos','imoveis')
--  order by tablename, policyname;
