-- ──────────────────────────────────────────────────────────────────────────
-- Backfill de `oportunidades.contacto_id` (histórico) — a correr DEPOIS da 0046.
--
-- Corre-se à mão no editor SQL, PASSO A PASSO (cada bloco separado, com o SELECT
-- de verificação). Idempotente: só toca em `contacto_id IS NULL`, por isso pode
-- voltar a correr-se, e nunca sobrepõe um elo vindo do eGO ('ego_link').
--
-- Regra canónica (decidida com o utilizador): para uma chave (telefone/email/nome)
-- que casa com várias linhas de `contactos`:
--   * só 1 linha            -> essa;
--   * várias, mas EXACTAMENTE 1 tem `ego_link` -> essa (a identidade real do eGO);
--   * senão                 -> ambíguo, não se liga.
-- Camadas por ordem de confiança, gravadas em `contacto_match`:
--   telefone (últimos 9 dígitos) > email > nome (baixa confiança: homónimos).
--
-- Medido a 01/10 (só leitura): telefone ~11 900, email ~700, nome ~8 700, sem
-- resolução ~4 800 (82% resolvíveis; 48% de alta confiança).
--
-- Desfazer só a camada fraca:  update oportunidades set contacto_id = null,
--   contacto_match = null where contacto_match = 'nome';  (e voltar a propagar)
-- ──────────────────────────────────────────────────────────────────────────

set statement_timeout = '300s';

-- `trg_oportunidades_updated` (set_atualizado_em) carimbava ~21 000 oportunidades como
-- "actualizadas agora" e podia disparar reprocessamentos em quem lê `atualizado_em`
-- (portal do Miguel). Desliga-se SÓ durante os passos 1-3 e volta a ligar-se logo a seguir.
-- Correr fora das janelas dos syncs (03:37 e 05:07 UTC). Se algo falhar a meio, ligar à mão:
--   alter table oportunidades enable trigger trg_oportunidades_updated;
alter table oportunidades disable trigger trg_oportunidades_updated;

-- ══ PASSO 1 — telefone ═════════════════════════════════════════════════════
create temp table _k_tel as
with k as (
  select right(regexp_replace(telefone, '\D', '', 'g'), 9) as chave, id, ego_link from public.contactos
   where length(regexp_replace(coalesce(telefone, ''), '\D', '', 'g')) >= 9
  union all
  select right(regexp_replace(telemovel, '\D', '', 'g'), 9), id, ego_link from public.contactos
   where length(regexp_replace(coalesce(telemovel, ''), '\D', '', 'g')) >= 9
), d as (select distinct chave, id, ego_link from k)
select chave,
       case when count(*) = 1 then (array_agg(id))[1]
            when count(*) filter (where ego_link is not null) = 1
              then (array_agg(id) filter (where ego_link is not null))[1]
       end as contacto_id
  from d group by chave;

update oportunidades o
   set contacto_id = k.contacto_id, contacto_match = 'telefone'
  from _k_tel k
 where o.contacto_id is null and k.contacto_id is not null
   and length(regexp_replace(coalesce(o.cliente_telefone, ''), '\D', '', 'g')) >= 9
   and right(regexp_replace(o.cliente_telefone, '\D', '', 'g'), 9) = k.chave;

select contacto_match, count(*) from oportunidades group by 1 order by 2 desc;   -- esperado: telefone ~11 900

-- ══ PASSO 2 — email ════════════════════════════════════════════════════════
create temp table _k_mail as
with d as (select distinct lower(trim(email)) as chave, id, ego_link from public.contactos where coalesce(trim(email), '') <> '')
select chave,
       case when count(*) = 1 then (array_agg(id))[1]
            when count(*) filter (where ego_link is not null) = 1
              then (array_agg(id) filter (where ego_link is not null))[1]
       end as contacto_id
  from d group by chave;

update oportunidades o
   set contacto_id = k.contacto_id, contacto_match = 'email'
  from _k_mail k
 where o.contacto_id is null and k.contacto_id is not null
   and coalesce(trim(o.cliente_email), '') <> '' and lower(trim(o.cliente_email)) = k.chave;

select contacto_match, count(*) from oportunidades group by 1 order by 2 desc;   -- esperado: email ~700

-- ══ PASSO 3 — nome (BAIXA CONFIANÇA — rever a amostra antes de manter) ═════
create temp table _k_nome as
with d as (select distinct lower(regexp_replace(trim(nome), '\s+', ' ', 'g')) as chave, id, ego_link
             from public.contactos where coalesce(trim(nome), '') <> '')
select chave,
       case when count(*) = 1 then (array_agg(id))[1]
            when count(*) filter (where ego_link is not null) = 1
              then (array_agg(id) filter (where ego_link is not null))[1]
       end as contacto_id
  from d group by chave;

update oportunidades o
   set contacto_id = k.contacto_id, contacto_match = 'nome'
  from _k_nome k
 where o.contacto_id is null and k.contacto_id is not null
   and coalesce(trim(o.cliente_nome), '') <> ''
   and lower(regexp_replace(trim(o.cliente_nome), '\s+', ' ', 'g')) = k.chave;

select contacto_match, count(*) from oportunidades group by 1 order by 2 desc;   -- esperado: nome ~8 700

alter table oportunidades enable trigger trg_oportunidades_updated;   -- volta a ligar
select t.tgname, t.tgenabled from pg_trigger t join pg_class c on c.oid = t.tgrelid
 where c.relname = 'oportunidades' and not t.tgisinternal;               -- tgenabled = 'O'

-- Amostra para olhar antes de aceitar a camada 'nome' (cliente_nome vs contacto):
select o.oportunidade_ref, o.cliente_nome, c.nome as contacto_nome, c.ego_link is not null as canonico
  from oportunidades o join public.contactos c on c.id = o.contacto_id
 where o.contacto_match = 'nome' order by random() limit 20;

-- ══ PASSO 4 — propagar para tarefas / notas / visitas ══════════════════════
select propagar_contacto_id();   -- ~23 700 tarefas, ~103 500 notas, ~1 800 visitas (no máximo)

-- Verificação final (a junção que o pedido queria):
select 'oportunidades' as tabela, count(*) as linhas, count(contacto_id) as com_contacto from oportunidades
union all select 'tarefas',  count(*), count(contacto_id) from tarefas
union all select 'notas',    count(*), count(contacto_id) from notas
union all select 'visitas',  count(*), count(contacto_id) from visitas;

select t.tarefa_titulo, c.nome from tarefas t join public.contactos c on c.id = t.contacto_id limit 20;
