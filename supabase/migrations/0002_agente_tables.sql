-- ════════════════════════════════════════════════
-- FIGUEIRA HOME — Tabelas do Agente (prefixo agente_)
-- Criadas em paralelo ao schema existente.
-- ════════════════════════════════════════════════

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
-- AGENTE_IMOVEIS
-- ──────────────────────────────────────────────
create table agente_imoveis (
  id              uuid primary key default uuid_generate_v4(),
  referencia      text,
  tipo            text,        -- 'apartamento' | 'moradia' | 'terreno' | 'comercial'
  fonte           text not null default 'manual',
  localizacao     text,
  preco           numeric,
  area            numeric,
  quartos         integer,
  descricao       text,
  fotos           jsonb default '[]'::jsonb,
  estado          text default 'disponivel',
  criado_em       timestamptz default now(),
  atualizado_em   timestamptz default now()
);

-- ──────────────────────────────────────────────
-- AGENTE_LEADS
-- ──────────────────────────────────────────────
create table agente_leads (
  id              uuid primary key default uuid_generate_v4(),
  cliente_id      uuid references agente_clientes(id) on delete cascade,
  imovel_id       uuid references agente_imoveis(id) on delete set null,
  estado          text default 'novo',
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
  canal           text not null,   -- 'web' | 'whatsapp' | 'telegram' | 'email'
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
  agente          text not null unique,  -- 'voz' | 'broker'
  persona         text,
  instrucoes      text,
  idioma          text default 'pt-PT',
  ativo           boolean default true,
  atualizado_em   timestamptz default now()
);

-- ──────────────────────────────────────────────
-- Dados iniciais
-- ──────────────────────────────────────────────
insert into agente_config (agente, persona, instrucoes) values
('voz',
 'Assistente de atendimento simpático e profissional da agência Figueirahome.',
 'Atende chamadas em Português de Portugal. Sê cordial e eficiente. Recolhe nome, contacto, tipo de interesse, orçamento e zona preferida. Confirma os dados antes de terminar.'),
('broker',
 'Assistente interno que ajuda o broker a consultar dados de clientes, imóveis e leads.',
 'Responde sempre em Português de Portugal. Consulta a base de dados antes de responder. Sê directo e preciso.');

-- ──────────────────────────────────────────────
-- Índices
-- ──────────────────────────────────────────────
create index idx_agente_leads_cliente on agente_leads(cliente_id);
create index idx_agente_leads_imovel on agente_leads(imovel_id);
create index idx_agente_chamadas_cliente on agente_chamadas(cliente_id);
create index idx_agente_imoveis_estado on agente_imoveis(estado);
create index idx_agente_conversas_canal on agente_conversas(canal);
