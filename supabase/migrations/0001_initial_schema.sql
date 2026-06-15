-- ════════════════════════════════════════════════
-- FIGUEIRA HOME — Schema inicial
-- ════════════════════════════════════════════════

-- Extensão para gerar UUIDs
create extension if not exists "uuid-ossp";

-- ──────────────────────────────────────────────
-- CLIENTES
-- ──────────────────────────────────────────────
create table clientes (
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
-- IMOVEIS
-- ──────────────────────────────────────────────
create table imoveis (
  id              uuid primary key default uuid_generate_v4(),
  referencia      text,
  tipo            text,        -- 'apartamento' | 'moradia' | 'terreno' | 'comercial' | ...
  fonte           text not null default 'manual',
                               -- 'idealista' | 'imovirtual' | 'agente_voz' | 'manual' | 'csv'
  localizacao     text,
  preco           numeric,
  area            numeric,     -- m2
  quartos         integer,
  descricao       text,
  fotos           jsonb default '[]'::jsonb,
  estado          text default 'disponivel',   -- 'disponivel' | 'reservado' | 'vendido'
  criado_em       timestamptz default now(),
  atualizado_em   timestamptz default now()
);

-- ──────────────────────────────────────────────
-- LEADS
-- ──────────────────────────────────────────────
create table leads (
  id              uuid primary key default uuid_generate_v4(),
  cliente_id      uuid references clientes(id) on delete cascade,
  imovel_id       uuid references imoveis(id) on delete set null,
  estado          text default 'novo',   -- 'novo' | 'contactado' | 'visita' | 'proposta' | 'fechado' | 'perdido'
  notas           text,
  criado_em       timestamptz default now(),
  atualizado_em   timestamptz default now()
);

-- ──────────────────────────────────────────────
-- CHAMADAS
-- ──────────────────────────────────────────────
create table chamadas (
  id              uuid primary key default uuid_generate_v4(),
  cliente_id      uuid references clientes(id) on delete set null,
  call_control_id text,        -- id da chamada na Telnyx
  numero_origem   text,
  duracao         integer,     -- segundos
  transcricao     text,
  resumo_ia       text,
  gravacao_url    text,
  data_hora       timestamptz default now()
);

-- ──────────────────────────────────────────────
-- CONVERSAS (Agente 2)
-- ──────────────────────────────────────────────
create table conversas (
  id              uuid primary key default uuid_generate_v4(),
  canal           text not null,   -- 'web' | 'whatsapp' | 'telegram' | 'email'
  participante    text,
  mensagens       jsonb default '[]'::jsonb,  -- [{role, content, timestamp}, ...]
  criado_em       timestamptz default now(),
  atualizado_em   timestamptz default now()
);

-- ──────────────────────────────────────────────
-- CONFIG_AGENTES
-- ──────────────────────────────────────────────
create table config_agentes (
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
insert into config_agentes (agente, persona, instrucoes) values
('voz',
 'Assistente de atendimento simpático e profissional da agência Figueirahome.',
 'Atende chamadas em Português de Portugal. Sê cordial e eficiente. Recolhe nome, contacto, tipo de interesse, orçamento e zona preferida. Confirma os dados antes de terminar.'),
('broker',
 'Assistente interno que ajuda o broker a consultar dados de clientes, imóveis e leads.',
 'Responde sempre em Português de Portugal. Consulta a base de dados antes de responder. Sê directo e preciso.');

-- ──────────────────────────────────────────────
-- Índices
-- ──────────────────────────────────────────────
create index idx_leads_cliente on leads(cliente_id);
create index idx_leads_imovel on leads(imovel_id);
create index idx_chamadas_cliente on chamadas(cliente_id);
create index idx_imoveis_estado on imoveis(estado);
create index idx_imoveis_fonte on imoveis(fonte);
create index idx_conversas_canal on conversas(canal);
