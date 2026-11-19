-- ════════════════════════════════════════════════
-- #58 F3 (2.ª passagem) — limpar as fichas de `contactos` com `telefone` fora da regra da 0058 (18/11/2026)
-- ════════════════════════════════════════════════
-- Contexto: docs/fases/telefone-ficha-antiga-plano.md. A passagem de 09/11 limpou 84 das 168; sobram 84, medidas a 19/11:
--   B  14  dois números válidos colados (9+9, 12+12, 14+14)
--   B' 15  18 dígitos que parecem 9+9 mas não passam na validação (começam por dígito fora de 2/3/9)
--   D   3  lista com vírgula/barra, 2 números
--   C  52  16 a 40 dígitos sem padrão → NÃO se tocam; vão ao Miguel (bloco 3)
--
-- Regra única, como a 0059: SÓ ACRESCENTAR. `telefone` := 1.º número; o 2.º vai para `telemovel` (se vazio) ou acrescenta-se
-- à lista dele (`telemovel || ', ' || nº`), se ainda não lá estiver. Nunca se apaga nada. Chave `(nome, criado_em)` e
-- `ego_atualizado_em` não mudam; atualiza-se por `id`.
-- Cada UPDATE está dentro de um bloco que ABORTA (rollback) se o nº de linhas não for o esperado.
-- Corre por partes, vendo o resultado de cada uma. Os telefones só aparecem no teu ecrã: ao colar resultados no chat, só contagens.

-- 0. Só leitura: triggers de `contactos` (ver se algum copia o telefone ou dispara IA no UPDATE) e quantas fichas estão fora.
select t.tgname, t.tgenabled, pg_get_triggerdef(t.oid) as definicao
  from pg_trigger t join pg_class c on c.oid = t.tgrelid
 where c.relname = 'contactos' and not t.tgisinternal
 order by t.tgname;

select count(*) as fora_da_regra   -- esperado: 84
  from public.contactos
 where length(regexp_replace(coalesce(telefone, ''), '\D', '', 'g')) > 15 or telefone ~ '[,;/]';

-- 1a. PRÉ-VISUALIZAÇÃO grupos B e D (esperado: 17 linhas = 14 B + 3 D). Não escreve nada.
with b as (
  select id, telefone, telemovel,
         regexp_replace(coalesce(telefone, ''), '\D', '', 'g') as d,
         regexp_split_to_array(btrim(coalesce(telefone, '')), '\s*[,;/]\s*') as ps
    from public.contactos
   where length(regexp_replace(coalesce(telefone, ''), '\D', '', 'g')) > 15 or telefone ~ '[,;/]'
), alvo as (
  select id, telemovel, 'D' as grupo, ps[1] as t1, ps[2] as t2 from b
   where telefone ~ '[,;/]' and array_length(ps, 1) = 2
  union all
  select id, telemovel, 'B', left(d, length(d) / 2), right(d, length(d) / 2) from b
   where telefone !~ '[,;/]' and length(d) in (18, 24, 28)
     and regexp_replace(left(d, length(d) / 2), '^00', '')  ~ '^([239][0-9]{8}|351[0-9]{9}|[0-9]{10,15})$'
     and regexp_replace(right(d, length(d) / 2), '^00', '') ~ '^([239][0-9]{8}|351[0-9]{9}|[0-9]{10,15})$'
)
select id, grupo, t1 as novo_telefone,
       case when btrim(coalesce(telemovel, '')) = '' then t2
            when regexp_replace(t1, '\D', '', 'g') = regexp_replace(t2, '\D', '', 'g') then telemovel
            when regexp_replace(telemovel, '\D', '', 'g') like '%' || right(regexp_replace(t2, '\D', '', 'g'), 9) || '%' then telemovel
            else telemovel || ', ' || t2 end as novo_telemovel,
       telemovel as telemovel_atual
  from alvo order by grupo, id;

-- 1b. UPDATE grupos B e D. Aborta se não forem exatamente 17 linhas (muda o número se a 1a mostrou outro).
do $$
declare v_n int;
begin
  with b as (
    select id, telefone, telemovel,
           regexp_replace(coalesce(telefone, ''), '\D', '', 'g') as d,
           regexp_split_to_array(btrim(coalesce(telefone, '')), '\s*[,;/]\s*') as ps
      from public.contactos
     where length(regexp_replace(coalesce(telefone, ''), '\D', '', 'g')) > 15 or telefone ~ '[,;/]'
  ), alvo as (
    select id, telemovel, ps[1] as t1, ps[2] as t2 from b
     where telefone ~ '[,;/]' and array_length(ps, 1) = 2
    union all
    select id, telemovel, left(d, length(d) / 2), right(d, length(d) / 2) from b
     where telefone !~ '[,;/]' and length(d) in (18, 24, 28)
       and regexp_replace(left(d, length(d) / 2), '^00', '')  ~ '^([239][0-9]{8}|351[0-9]{9}|[0-9]{10,15})$'
       and regexp_replace(right(d, length(d) / 2), '^00', '') ~ '^([239][0-9]{8}|351[0-9]{9}|[0-9]{10,15})$'
  )
  update public.contactos c
     set telefone = a.t1,
         telemovel = case when btrim(coalesce(a.telemovel, '')) = '' then a.t2
                          when regexp_replace(a.t1, '\D', '', 'g') = regexp_replace(a.t2, '\D', '', 'g') then a.telemovel
                          when regexp_replace(a.telemovel, '\D', '', 'g') like '%' || right(regexp_replace(a.t2, '\D', '', 'g'), 9) || '%' then a.telemovel
                          else a.telemovel || ', ' || a.t2 end
    from alvo a where c.id = a.id;
  get diagnostics v_n = row_count;
  if v_n <> 17 then raise exception 'ABORTADO: % linhas em vez de 17 (rollback feito)', v_n; end if;
  raise notice 'OK 1b: % fichas corrigidas', v_n;
end $$;

-- 2a. PRÉ-VISUALIZAÇÃO grupo B' (esperado: 15 linhas, 18 dígitos). Mostra o 1.º dígito de cada metade para decidir se são
--     números reais com um prefixo fora do comum (ex.: 6, 7) ou lixo. Só avança para a 2b se te parecerem dois números.
with b as (
  select id, regexp_replace(coalesce(telefone, ''), '\D', '', 'g') as d
    from public.contactos
   where length(regexp_replace(coalesce(telefone, ''), '\D', '', 'g')) = 18 and telefone !~ '[,;/]'
)
select left(d, 1) as inicio_1, left(right(d, 9), 1) as inicio_2, count(*) as n
  from b
 where not (regexp_replace(left(d, 9), '^00', '') ~ '^([239][0-9]{8}|351[0-9]{9}|[0-9]{10,15})$'
        and regexp_replace(right(d, 9), '^00', '') ~ '^([239][0-9]{8}|351[0-9]{9}|[0-9]{10,15})$')
 group by 1, 2 order by n desc;

-- 2b. UPDATE grupo B' (só depois de veres a 2a; mesma regra «só acrescentar»). Aborta se não forem 15 linhas.
do $$
declare v_n int;
begin
  with b as (
    select id, telemovel, regexp_replace(coalesce(telefone, ''), '\D', '', 'g') as d
      from public.contactos
     where length(regexp_replace(coalesce(telefone, ''), '\D', '', 'g')) = 18 and telefone !~ '[,;/]'
  ), alvo as (
    select id, telemovel, left(d, 9) as t1, right(d, 9) as t2 from b
     where not (regexp_replace(left(d, 9), '^00', '') ~ '^([239][0-9]{8}|351[0-9]{9}|[0-9]{10,15})$'
            and regexp_replace(right(d, 9), '^00', '') ~ '^([239][0-9]{8}|351[0-9]{9}|[0-9]{10,15})$')
  )
  update public.contactos c
     set telefone = a.t1,
         telemovel = case when btrim(coalesce(a.telemovel, '')) = '' then a.t2
                          when a.t1 = a.t2 then a.telemovel
                          when regexp_replace(a.telemovel, '\D', '', 'g') like '%' || a.t2 || '%' then a.telemovel
                          else a.telemovel || ', ' || a.t2 end
    from alvo a where c.id = a.id;
  get diagnostics v_n = row_count;
  if v_n <> 15 then raise exception 'ABORTADO: % linhas em vez de 15 (rollback feito)', v_n; end if;
  raise notice 'OK 2b: % fichas corrigidas', v_n;
end $$;

-- 3. O QUE SOBRA (esperado: 52, o grupo C) = lista para o Miguel/consultora dizerem o número certo. Só leitura.
--    Para cada ficha: qual é o telefone correto? Respondido, corrige-se `telefone` (um só número, ≤15 dígitos).
select id, nome, criado_em, ego_link is not null as tem_ego_link, telefone, telemovel
  from public.contactos
 where length(regexp_replace(coalesce(telefone, ''), '\D', '', 'g')) > 15 or telefone ~ '[,;/]'
 order by nome;

-- 4. SÓ DEPOIS de o bloco 3 devolver 0 linhas: validar a restrição da 0058 (se a 0058 ainda não foi corrida, corre-a antes).
--    alter table public.contactos validate constraint contactos_telefone_um_numero;

-- Reverter 1b/2b: não há (só se acrescenta; o 2.º número ficou em `telemovel`). O texto original do `telefone` é o 1.º+2.º
-- números colados, recuperável juntando `telefone` e o último número de `telemovel`.
