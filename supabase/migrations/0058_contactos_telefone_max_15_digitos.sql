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
-- O bloco 1 recusa-se a correr enquanto houver linhas fora da regra.
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

-- 1. A restrição. Falha de propósito se ainda houver linhas fora da regra.
do $$
declare n int;
begin
  select count(*) into n from public.contactos
   where length(regexp_replace(coalesce(telefone, ''), '\D', '', 'g')) > 15 or telefone ~ '[,;/]';
  if n > 0 then
    raise exception 'ainda há % contactos com telefone fora da regra: corre a limpeza (F3) e confirma o scraper (F5) primeiro', n;
  end if;
end $$;

alter table public.contactos
  add constraint contactos_telefone_um_numero
  check (length(regexp_replace(coalesce(telefone, ''), '\D', '', 'g')) <= 15 and coalesce(telefone, '') !~ '[,;/]');

-- 2. Reverter (se o sync do scraper ou o pipeline do Miguel começarem a falhar):
--    alter table public.contactos drop constraint contactos_telefone_um_numero;
