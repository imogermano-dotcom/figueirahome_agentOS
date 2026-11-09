-- ════════════════════════════════════════════════
-- Migration 0058 — `contactos.telefone`: nunca mais de 15 dígitos nem vários números
-- ════════════════════════════════════════════════
-- Pedido #58 (docs/fases/telefone-ficha-antiga-plano.md). 99 fichas têm 18 dígitos em `telefone` (carga de 03/05/2026,
-- sem `ego_link`): dois números colados ou o mesmo duas vezes. O 1.º envio da Matilde foi para um deles (06/11).
-- Um E.164 tem no máximo 15 dígitos; mais do que isso nunca é um número só.
--
-- ⚠️ SÓ DEPOIS de: (1) o scraper deixar de copiar listas de números para `telefone` (fase F5 do plano) e (2) a limpeza
-- dos casos existentes (fase F3). Com a restrição ligada antes, o primeiro upsert do scraper de um contacto cujo
-- `telemovel` tem vários números («00351…, 00351…», 498 fichas hoje) rejeitava o LOTE INTEIRO e o sync parava.
-- Versão de 09/11: a F3 limpou 84 das 168 (aplicada); sobram 84 que não se adivinham (78 de 16–40 dígitos + 6 com
-- `telemovel` ocupado). Por isso a restrição entra `NOT VALID`: vale para todo o INSERT/UPDATE, mas não verifica as linhas
-- antigas. ⚠️ Um UPDATE a QUALQUER coluna de uma dessas 84 linhas vai falhar (o CHECK avalia a linha nova inteira) até
-- elas serem corrigidas; depois corre-se o bloco 3 (`validate constraint`).
--
-- Só `telefone`: `telemovel` guarda a lista de números do eGO tal como vem (de propósito, 498 linhas com vírgulas).
-- Corre por partes, vendo o resultado de cada uma.

-- 0. Só leitura: linhas que a regra rejeitaria (esperado antes da limpeza: 168; depois: 0) e os triggers de `contactos`.
select count(*) as fora_da_regra
  from public.contactos
 where length(regexp_replace(coalesce(telefone, ''), '\D', '', 'g')) > 15
    or telefone ~ '[,;/]';

select t.tgname, t.tgenabled, pg_get_triggerdef(t.oid) as definicao
  from pg_trigger t join pg_class c on c.oid = t.tgrelid
 where c.relname = 'contactos' and not t.tgisinternal
 order by t.tgname;

-- 1. A restrição, NOT VALID: as linhas antigas (as 84 por rever) não são verificadas; tudo o que se escreve daqui em diante é.
alter table public.contactos
  add constraint contactos_telefone_um_numero
  check (length(regexp_replace(coalesce(telefone, ''), '\D', '', 'g')) <= 15 and coalesce(telefone, '') !~ '[,;/]')
  not valid;

-- 2b. Verificação: quantas linhas ficam fora da regra (esperado 84) e se a restrição existe (convalidated = false).
select (select count(*) from public.contactos
         where length(regexp_replace(coalesce(telefone, ''), '\D', '', 'g')) > 15 or telefone ~ '[,;/]') as fora_da_regra,
       (select convalidated from pg_constraint where conname = 'contactos_telefone_um_numero') as validada;

-- 3. MAIS TARDE, depois de corrigir as 84 (e só então; falha enquanto houver uma): passa a restrição a validada.
--    alter table public.contactos validate constraint contactos_telefone_um_numero;

-- 2. Reverter (se o sync do scraper ou o pipeline do Miguel começarem a falhar):
--    alter table public.contactos drop constraint contactos_telefone_um_numero;
