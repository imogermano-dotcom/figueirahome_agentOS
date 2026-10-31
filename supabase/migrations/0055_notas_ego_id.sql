-- 0055: id da nota no eGO (fase A2, docs/fases/ego-api-notas-plano.md).
-- Corrida à mão no editor SQL do Supabase. Só acrescenta; não altera nem apaga dados.

-- 1. Coluna nova, vazia em todas as linhas existentes. Acrescentar uma coluna nula é só metadados (instantâneo, sem reescrever a tabela).
alter table notas add column if not exists nota_ego_id bigint;

-- 2. Unicidade pelo id da nota, só onde existe. Linhas antigas (NULL) não entram no índice, por isso nada pode falhar.
--    É a chave que a API do eGO garante estável e que acaba com os duplicados por texto repetido (as notas novas).
create unique index if not exists uq_notas_ego_id on notas(nota_ego_id) where nota_ego_id is not null;

-- Verificação: a coluna existe e está toda a NULL; o índice foi criado.
select count(*) as linhas, count(nota_ego_id) as com_ego_id from notas;
select indexname from pg_indexes where tablename = 'notas' and indexname = 'uq_notas_ego_id';
