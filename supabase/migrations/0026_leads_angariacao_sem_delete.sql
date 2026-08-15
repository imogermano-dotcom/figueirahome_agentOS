-- ════════════════════════════════════════════════
-- Migration 0026 — tirar o DELETE anónimo a `leads_angariacao`
-- (projecto UNIFICADO, zphasvfopnbzwnaidsnw)
-- ════════════════════════════════════════════════
-- Encontrada a 2026-08-15, ao varrer as políticas depois da `0025`: a política
-- `leads_ang_write` é `for all` com `roles = {public}` e `using (true)`.
-- `leads_angariacao` tem as **79 leads do fluxo humano** (Make + consultora ao
-- telefone) com nome, telefone e o trabalho feito em cima delas. `for all`
-- inclui DELETE: qualquer pessoa com a chave `anon` deste projecto podia
-- apagá-las todas.
--
-- Ao contrário de `contactos` (migration 0025), aqui **não se pode tirar toda a
-- escrita**. Confirmado com o utilizador a 2026-08-15, e a distinção importa:
--
--   * o Make escreve em `leads` com a **`service_role`** (bypassa RLS);
--   * mas os fluxos de **angariação** escrevem em `leads_angariacao` com a
--     chave **`anon`** — e portanto dependem mesmo desta política.
--
-- É por isso que `leads_ang_write` existe: ao contrário do
-- "service role full access" da 0025, que era um mal-entendido, esta foi criada
-- por uma necessidade real. Tirar o INSERT ou o UPDATE pararia a entrada de
-- leads de angariação em silêncio.
--
-- Sobra o DELETE, que nenhum fluxo usa e é a única das quatro operações
-- irreversível. SELECT, INSERT e UPDATE ficam exactamente como estavam.
--
-- Consequência a registar: a chave `anon` deste projecto está no Make. Não está
-- publicada, mas existe fora do código — o que torna as políticas abertas a
-- `anon` risco real e não teórico.

drop policy if exists "leads_ang_write" on leads_angariacao;

-- O que `leads_ang_write` já permitia, menos o DELETE. Uma política por verbo,
-- porque `for all` não sabe excluir um.
drop policy if exists "leads_ang_select" on leads_angariacao;
create policy "leads_ang_select" on leads_angariacao
  for select to public using (true);

drop policy if exists "leads_ang_insert" on leads_angariacao;
create policy "leads_ang_insert" on leads_angariacao
  for insert to public with check (true);

drop policy if exists "leads_ang_update" on leads_angariacao;
create policy "leads_ang_update" on leads_angariacao
  for update to public using (true) with check (true);

-- O painel autenticado continua com acesso total, incluindo apagar.
drop policy if exists "auth_full_access" on leads_angariacao;
create policy "auth_full_access" on leads_angariacao
  for all to authenticated using (true) with check (true);

-- ── O PASSO SEGUINTE, a falar com o Miguel ───────────────────────────────
-- Porque é que o fluxo de angariação usa `anon` e o de `leads` usa
-- `service_role` — se for só história, passar os dois para o mesmo caminho
-- fecha `leads_ang_insert`/`leads_ang_update` e deixa a tabela só de leitura.
-- Enquanto não se souber, não tirar mais nada: falha em silêncio.

-- ── VERIFICAÇÃO ──────────────────────────────────────────────────────────
-- DELETE anónimo já não deve aparecer em `leads_angariacao`:
--
-- select tablename, policyname, cmd, roles::text
-- from pg_policies
-- where schemaname = 'public'
--   and cmd in ('ALL','DELETE')
--   and (roles::text like '%anon%' or roles::text like '%public%')
--   and coalesce(qual::text, '') !~ 'auth\.uid|auth\.jwt|auth\.role';
--
-- E confirmar que ficaram as três + auth:
-- select policyname, cmd, roles::text from pg_policies
--  where schemaname='public' and tablename='leads_angariacao' order by policyname;
