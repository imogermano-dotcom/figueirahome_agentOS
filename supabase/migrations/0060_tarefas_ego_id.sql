-- ════════════════════════════════════════════════
-- Migration 0060 — `tarefas.ego_id`: o id da tarefa no eGO
-- ════════════════════════════════════════════════
-- Pedido #8 (docs/fases/tarefas-pela-api-plano.md, F2.5). A API do eGO (`ListTaskByPage`) dá o `id` de cada tarefa; hoje só
-- se guarda a chave `(oportunidade_ref, tarefa_titulo, tarefa_due_raw)`, por isso uma tarefa reagendada aparece como nova.
-- Passo 1: o sync passa a gravar a coluna (a chave de upsert não muda). Nada se apaga e nada se reescreve: coluna nova, a NULL.
--
-- ⚠️ ORDEM: esta migration ANTES do deploy do código. Com o código novo e sem a coluna, o upsert das tarefas falha e o cron para.
-- Corre por partes, vendo o resultado de cada uma.

-- 1. A coluna e um índice SIMPLES (não único). Único só no passo 2: uma tarefa reagendada mantém o id mas muda a chave, o upsert
--    por chave insere uma linha nova com o mesmo `ego_id` da antiga, e um índice único rejeitaria o lote inteiro (cron parado).
alter table public.tarefas add column if not exists ego_id bigint;
create index if not exists tarefas_ego_id_idx on public.tarefas (ego_id);

-- 2. Verificação: a coluna existe e está toda a NULL (esperado: com_ego_id = 0 antes do deploy).
select (select count(*) from public.tarefas) as linhas,
       (select count(*) from public.tarefas where ego_id is not null) as com_ego_id,
       (select count(*) from pg_indexes where indexname = 'tarefas_ego_id_idx') as indice;

-- 3. Reverter (se alguma coisa correr mal): o código novo tem de estar fora de produção antes.
--    drop index if exists public.tarefas_ego_id_idx;
--    alter table public.tarefas drop column if exists ego_id;
