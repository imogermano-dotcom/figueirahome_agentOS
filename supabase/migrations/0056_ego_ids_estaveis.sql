-- 0056: ids estáveis do eGO (pedido #27, docs/fases/ego-ids-estaveis-plano.md).
-- Corrida à mão no editor SQL do Supabase, por partes (1 a 4), vendo o resultado de cada uma. Só acrescenta colunas e preenche NULL.

-- 1. Colunas novas (nulas em todas as linhas; instantâneo).
alter table oportunidades add column if not exists ego_lead_id   bigint;
alter table contactos     add column if not exists ego_person_id bigint;

-- 2. Backfill a partir do URL que a linha já tem. Só preenche onde está NULL; nunca altera outras colunas.
--    oportunidades tem BEFORE UPDATE que carimba atualizado_em (o portal do Miguel pode lê-la): desligado durante o UPDATE e religado no fim.
--    Duas formas de URL: /egocore/Leads/N e /egocore/lead/N.
alter table oportunidades disable trigger trg_oportunidades_updated;

update oportunidades
   set ego_lead_id = (substring(url from '/[Ll]eads?/([0-9]+)'))::bigint
 where ego_lead_id is null
   and url ~ '/[Ll]eads?/[0-9]+';

alter table oportunidades enable trigger trg_oportunidades_updated;

update contactos
   set ego_person_id = (substring(ego_link from '/person/([0-9]+)'))::bigint
 where ego_person_id is null
   and ego_link ~ '/person/[0-9]+';

-- 3. Unicidade, só onde há valor. Criada DEPOIS do backfill: se houvesse repetidos falhava aqui, sem deixar nada a meio.
create unique index if not exists uq_oportunidades_ego_lead_id on oportunidades(ego_lead_id) where ego_lead_id is not null;
create unique index if not exists uq_contactos_ego_person_id   on contactos(ego_person_id)   where ego_person_id is not null;

-- 4. Verificação. Esperado (medido a 01/11): oportunidades 21 769 com id; contactos 12 742 com id; trigger 'O' (ligado).
select count(*) as oportunidades, count(ego_lead_id) as com_ego_lead_id from oportunidades;
select count(*) as contactos, count(ego_person_id) as com_ego_person_id from public.contactos;
select t.tgname, t.tgenabled from pg_trigger t join pg_class c on c.oid = t.tgrelid
 where c.relname = 'oportunidades' and t.tgname = 'trg_oportunidades_updated';
select indexname from pg_indexes where indexname in ('uq_oportunidades_ego_lead_id', 'uq_contactos_ego_person_id');
