-- ════════════════════════════════════════════════
-- SUPERSEDIDA por 0006_unificar_tabelas.sql — NÃO CORRER.
-- agente_tarefas passou a viver no projecto secundário (imóveis) junto
-- com o resto das tabelas unificadas. Ficheiro mantido só por histórico.
-- ════════════════════════════════════════════════
-- Migration 0005 — agente_tarefas (projecto PRINCIPAL Supabase) [OBSOLETO]
-- ════════════════════════════════════════════════
-- Entidade genérica de tarefas — não exclusiva de imóveis. imovel_ref é
-- texto solto, sem FK real: a tabela `imoveis` vive no projecto SECUNDÁRIO
-- Supabase, não há FK entre projectos diferentes.

create table agente_tarefas (
  id            uuid primary key default uuid_generate_v4(),
  titulo        text not null,
  descricao     text,
  imovel_ref    text,                       -- sem FK: imoveis vive noutro projecto Supabase
  estado        text default 'pendente',    -- 'pendente' | 'em_curso' | 'concluida' | 'cancelada'
  prazo         date,
  responsavel   text,
  criado_em     timestamptz default now(),
  atualizado_em timestamptz default now()
);

create index idx_agente_tarefas_estado on agente_tarefas(estado);
create index idx_agente_tarefas_imovel on agente_tarefas(imovel_ref);

alter table agente_tarefas enable row level security;
create policy auth_full_access on agente_tarefas for all to authenticated using (true) with check (true);
