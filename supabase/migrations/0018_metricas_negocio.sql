-- ════════════════════════════════════════════════
-- Migration 0018 — colunas p/ métricas de negócio (projecto SECUNDÁRIO)
-- ════════════════════════════════════════════════
-- Prepara os 4 blocos da aba Métricas. Só ALTER TABLE ADD COLUMN e um índice:
-- nada é apagado nem reescrito, e ambas as tabelas estão vazias hoje.
--
-- Reversível com:
--   alter table agente_interacoes drop column tools_detalhe;
--   alter table agente_tarefas drop column tipo, drop column agente,
--                              drop column conversa_id, drop column motivo;

-- ── (a) Argumentos das tools ─────────────────────
-- `tools_usadas` guarda só os NOMES; os argumentos de `pesquisar_imoveis`
-- (zona, quartos, preco_max) eram descartados no engine. São eles o bloco
-- inteiro de "preferências de mercado" — e valem mais que `agente_clientes`,
-- porque captam o que toda a gente procurou, não só quem ficou registado.
--
-- Formato: [{"nome": "pesquisar_imoveis", "input": {"zona": "Figueira", ...}}]
-- Só tools de pesquisa trazem `input` — ver _TOOLS_INPUT_SEGURO no engine.
-- Nenhum dado pessoal entra aqui.
alter table agente_interacoes add column if not exists tools_detalhe jsonb;

comment on column agente_interacoes.tools_detalhe is
  'Tools chamadas com argumentos. Só tools de pesquisa trazem input — nunca PII.';

-- ── (b) Tarefas atribuíveis ──────────────────────
-- Visitas e escaladas distinguiam-se por ILIKE no `titulo` ('Visita %',
-- '%ESCALAR —%'), e não havia forma de as ligar ao assistente ou à conversa.
-- Sem isto não há taxa de conversão por assistente nem motivos de transbordo
-- agregáveis — e mudar o formato do título partia as métricas em silêncio.
alter table agente_tarefas add column if not exists tipo text;         -- visita | escalar
alter table agente_tarefas add column if not exists agente text;       -- a1_vendedor | a2_geral
alter table agente_tarefas add column if not exists conversa_id uuid
  references agente_conversas(id) on delete set null;
alter table agente_tarefas add column if not exists motivo text;

comment on column agente_tarefas.tipo is
  'visita | escalar — antes só dava para inferir do titulo por ILIKE.';
comment on column agente_tarefas.conversa_id is
  'Null quando a tarefa nasce no 1.º turno de uma conversa nova (o id só existe depois do save_conversation).';

create index if not exists idx_agente_tarefas_tipo_agente
  on agente_tarefas (tipo, agente, criado_em desc);
