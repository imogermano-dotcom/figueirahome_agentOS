-- ════════════════════════════════════════════════
-- Migration 0006 — unificar tabelas do portal no projecto SECUNDÁRIO
-- (supabase_imoveis, onde já vive `imoveis`)
-- ════════════════════════════════════════════════
-- Recria agente_clientes/leads/chamadas/conversas/config (schema idêntico
-- ao projecto principal) + agente_tarefas (absorve 0005_agente_tarefas.sql,
-- que fica supersedida — não correr essa noutro lado).
-- Auth continua no projecto PRINCIPAL — só dados migram para aqui.

create extension if not exists "uuid-ossp";

-- ──────────────────────────────────────────────
-- AGENTE_CLIENTES
-- ──────────────────────────────────────────────
create table agente_clientes (
  id              uuid primary key default uuid_generate_v4(),
  nome            text,
  telefone        text,
  email           text,
  tipo_interesse  text,        -- 'compra' | 'arrendamento' | 'venda' | 'outro'
  orcamento       numeric,
  zona_preferida  text,
  notas           text,
  origem          text,        -- 'chamada' | 'manual' | 'chat'
  criado_em       timestamptz default now(),
  atualizado_em   timestamptz default now()
);

-- ──────────────────────────────────────────────
-- AGENTE_LEADS
-- imovel_id mantém-se uuid solto (sempre null na prática, sem FK) —
-- ligação leads↔imoveis fica para outra altura, fora de âmbito aqui.
-- ──────────────────────────────────────────────
create table agente_leads (
  id              uuid primary key default uuid_generate_v4(),
  cliente_id      uuid references agente_clientes(id) on delete cascade,
  imovel_id       uuid,
  estado          text default 'novo',   -- 'novo' | 'contactado' | 'visita' | 'proposta' | 'fechado' | 'perdido'
  notas           text,
  criado_em       timestamptz default now(),
  atualizado_em   timestamptz default now()
);

-- ──────────────────────────────────────────────
-- AGENTE_CHAMADAS
-- ──────────────────────────────────────────────
create table agente_chamadas (
  id              uuid primary key default uuid_generate_v4(),
  cliente_id      uuid references agente_clientes(id) on delete set null,
  call_control_id text,
  numero_origem   text,
  duracao         integer,
  transcricao     text,
  resumo_ia       text,
  gravacao_url    text,
  data_hora       timestamptz default now()
);

-- ──────────────────────────────────────────────
-- AGENTE_CONVERSAS
-- ──────────────────────────────────────────────
create table agente_conversas (
  id              uuid primary key default uuid_generate_v4(),
  canal           text not null,
  participante    text,
  mensagens       jsonb default '[]'::jsonb,
  criado_em       timestamptz default now(),
  atualizado_em   timestamptz default now()
);

-- ──────────────────────────────────────────────
-- AGENTE_CONFIG
-- ──────────────────────────────────────────────
create table agente_config (
  id              uuid primary key default uuid_generate_v4(),
  agente          text not null unique,
  persona         text,
  instrucoes      text,
  idioma          text default 'pt-PT',
  ativo           boolean default true,
  atualizado_em   timestamptz default now()
);

-- ──────────────────────────────────────────────
-- AGENTE_TAREFAS (absorve 0005_agente_tarefas.sql)
-- ──────────────────────────────────────────────
create table agente_tarefas (
  id            uuid primary key default uuid_generate_v4(),
  titulo        text not null,
  descricao     text,
  imovel_ref    text,                       -- sem FK: imoveis é tabela local aqui, mas ainda sem ligação formal
  estado        text default 'pendente',    -- 'pendente' | 'em_curso' | 'concluida' | 'cancelada'
  prazo         date,
  responsavel   text,
  criado_em     timestamptz default now(),
  atualizado_em timestamptz default now()
);

-- ──────────────────────────────────────────────
-- Índices
-- ──────────────────────────────────────────────
create index idx_agente_leads_cliente on agente_leads(cliente_id);
create index idx_agente_chamadas_cliente on agente_chamadas(cliente_id);
create index idx_agente_conversas_canal on agente_conversas(canal);
create index idx_agente_tarefas_estado on agente_tarefas(estado);
create index idx_agente_tarefas_imovel on agente_tarefas(imovel_ref);

-- ──────────────────────────────────────────────
-- RLS — mesmo padrão já usado no resto do projecto
-- (irrelevante para o backend, que usa sempre service_role_key, mas
-- mantém-se por consistência/defesa em profundidade)
-- ──────────────────────────────────────────────
alter table agente_clientes enable row level security;
alter table agente_leads enable row level security;
alter table agente_chamadas enable row level security;
alter table agente_conversas enable row level security;
alter table agente_config enable row level security;
alter table agente_tarefas enable row level security;

create policy auth_full_access on agente_clientes for all to authenticated using (true) with check (true);
create policy auth_full_access on agente_leads for all to authenticated using (true) with check (true);
create policy auth_full_access on agente_chamadas for all to authenticated using (true) with check (true);
create policy auth_full_access on agente_conversas for all to authenticated using (true) with check (true);
create policy auth_full_access on agente_config for all to authenticated using (true) with check (true);
create policy auth_full_access on agente_tarefas for all to authenticated using (true) with check (true);
