# Database Schema — Figueirahome Agent Call (Supabase / PostgreSQL)

> Estrutura completa da base de dados. Nomes de tabelas e colunas em português, snake_case. Todas as tabelas têm `id` UUID e `criado_em` timestamp por defeito.

## Dois projectos Supabase — o que vive onde (desde migration 0006, 2026-07-21)

- **Projecto UNIFICADO** (`supabase_imoveis_url/key` no `.env` — nome histórico, é o projecto principal de dados agora): todas as tabelas — `imoveis`, `agente_clientes`, `agente_leads`, `agente_chamadas`, `agente_conversas`, `agente_config`, `agente_tarefas`. `backend/app/db/supabase_client.py::get_supabase()` aponta para aqui.
- **Projecto ORIGINAL** (`supabase_url/key` — nome histórico, "principal"): fica **só como Auth** — as 10 contas de login dos corretores/admin vivem lá (Supabase não permite copiar hashes de password via API). `get_supabase_auth()` aponta para aqui, usado apenas em `deps.py::require_auth` para validar o token. Sem tabelas de dados novas aqui — as antigas (`agente_clientes` etc.) ficam como backup frio, não lidas nem escritas pelo backend.
- Isto funciona porque o backend usa sempre `service_role_key` para aceder a dados (nunca passa o JWT do utilizador ao Postgres) — a validação de RLS nunca chega a ser avaliada, por isso não há problema de "RLS não reconhece token doutro projecto".

---

## Visão geral das tabelas

| Tabela | Propósito |
|---|---|
| `clientes` | Pessoas que contactam ou são contactadas pela agência. |
| `imoveis` | Portefólio de imóveis, de várias fontes. |
| `leads` | Ligação entre um cliente e um imóvel/interesse. |
| `chamadas` | Histórico de chamadas atendidas pelo Agente 1. |
| `conversas` | Histórico de conversas do Agente 2, por canal. |
| `config_agentes` | Persona e instruções configuráveis de cada agente. |
| `agente_tarefas` | Tarefas genéricas (não exclusivas de imóveis) do corretor/agência. |

---

## Relações

```
clientes 1 ──── N leads N ──── 1 imoveis
clientes 1 ──── N chamadas
```

---

## SQL — Migrations

Guardar como `supabase/migrations/0001_initial_schema.sql`.

```sql
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
-- IMOVEIS — vive no PROJECTO SECUNDÁRIO Supabase
-- (supabase_imoveis_url/key, id zphasvfopnbzwnaidsnw), NÃO no principal.
-- Tabela real, alimentada originalmente por export do eGO Real Estate CRM.
-- Chave de negócio é `imovel_ref` (não há coluna `id` uuid separada).
-- Migration 0004 adiciona só `fonte`; o resto já existia em produção.
-- ──────────────────────────────────────────────
create table imoveis (
  imovel_ref            text primary key,
  natureza              text,        -- 'Apartamento' | 'Moradia' | ...
  disponibilidade       text,        -- 'Disponível' | 'Em Prospecção' | 'Por validar' | 'Retirado'
  estado                text,        -- condição: 'Novo' | 'Usado' | 'Renovado' | 'Recuperado' | ...
  fonte                 text not null default 'manual',
                                     -- 'egorealestate' | 'site_proprio' | 'idealista' | 'imovirtual' | 'manual' | 'csv'
  titulo                text,
  descricao             text,
  proprietario          text,
  angariador            text,
  vendedor              text,
  quartos               integer,
  casas_banho           integer,
  suites                integer,
  piso                  text,
  num_pisos             integer,
  numero                text,
  fracao                text,
  area_util             numeric,
  area_bruta            numeric,
  area_terreno          numeric,
  conservacao           text,
  certificacao_energetica text,
  venda_preco           numeric,
  arrendamento_preco    numeric,
  comissao_agencia      numeric,
  comissao_angariador   numeric,
  comissao_vendedor     numeric,
  exclusividade         text,
  morada                text,
  codigo_postal         text,
  concelho              text,
  freguesia             text,
  zona                  text,
  piscina               boolean,
  garagem                boolean,
  jardim                boolean,
  terraco               boolean,
  varanda                boolean,
  vista_mar             boolean,
  vista_praia           boolean,
  ar_condicionado       boolean,
  elevador              boolean,
  aquecimento_central   boolean,
  arrecadacao           boolean,
  estacionamento        boolean,
  portais               text,        -- lista de portais onde está syndicado (via eGO), texto separado por vírgulas
  foto_principal        text,
  fotos                 jsonb default '[]'::jsonb,   -- array de URLs (eGO CDN)
  ego_id                bigint,      -- ID da propriedade no eGO Real Estate (null = nunca sincronizado)
  ego_atualizado_em     timestamptz,
  data_criacao          date,
  data_alteracao        date
);
create unique index idx_imoveis_ego_id on imoveis(ego_id);  -- integridade (Postgres permite múltiplos NULL); sync eGO faz upsert por imovel_ref, não por este
-- `disponibilidade` tem 2 fontes: Web API pública do eGO (só publicados, `imoveis_sync.py::sync_egorealestate`)
-- e o backoffice autenticado (visibilidade total, incl. nunca-publicados; `imoveis_sync.py::validar_disponibilidade_crm`,
-- via `egorealestate_crm.py` — scraping de sessão, credenciais EGOREALESTATE_CRM_*). O backoffice é autoritativo.
create index idx_imoveis_fonte on imoveis(fonte);
create index idx_imoveis_disponibilidade on imoveis(disponibilidade);

-- ──────────────────────────────────────────────
-- LEADS
-- ──────────────────────────────────────────────
create table leads (
  id              uuid primary key default uuid_generate_v4(),
  cliente_id      uuid references clientes(id) on delete cascade,
  imovel_id       uuid,        -- sem FK, sempre null na prática hoje; ligação leads↔imoveis por fazer (fora de âmbito da migration 0006)
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
  participante    text,            -- identificador do interlocutor (nº, email, etc.)
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
  persona         text,                  -- descrição da personalidade
  instrucoes      text,                  -- instruções de comportamento (system prompt)
  idioma          text default 'pt-PT',
  ativo           boolean default true,
  atualizado_em   timestamptz default now()
);

-- ──────────────────────────────────────────────
-- Dados iniciais — config dos dois agentes
-- ──────────────────────────────────────────────
insert into config_agentes (agente, persona, instrucoes) values
('voz',
 'Assistente de atendimento simpático e profissional da agência Figueirahome.',
 'Atende chamadas em Português de Portugal. Sê cordial e eficiente. Recolhe nome, contacto, tipo de interesse, orçamento e zona preferida. Confirma os dados antes de terminar.'),
('broker',
 'Assistente interno que ajuda o broker a consultar dados de clientes, imóveis e leads.',
 'Responde sempre em Português de Portugal. Consulta a base de dados antes de responder. Sê directo e preciso.');

-- ──────────────────────────────────────────────
-- AGENTE_TAREFAS — migration 0005 (projecto PRINCIPAL)
-- Entidade genérica de tarefas, não exclusiva de imóveis.
-- ──────────────────────────────────────────────
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

-- ──────────────────────────────────────────────
-- Índices úteis
-- ──────────────────────────────────────────────
create index idx_leads_cliente on leads(cliente_id);
create index idx_leads_imovel on leads(imovel_id);
create index idx_chamadas_cliente on chamadas(cliente_id);
create index idx_conversas_canal on conversas(canal);
```

---

## Row Level Security (RLS)

> **ACTIVO desde Fase 4c** (`supabase/migrations/0003_rls.sql`).
> Backend usa `service_role_key` → bypass automático. Frontend nunca acede directamente.

### Estado actual — tabelas `agente_*`

| Tabela | RLS | Política |
|---|---|---|
| `agente_clientes` | ✅ | `auth_full_access` — authenticated |
| `agente_imoveis` | ✅ | **deprecated** (Fase A reformulação imóveis) — sem leitura/escrita nova, dashboard/API/broker usam `imoveis` no projecto secundário |
| `agente_leads` | ✅ | `auth_full_access` — authenticated |
| `agente_chamadas` | ✅ | `auth_full_access` — authenticated |
| `agente_conversas` | ✅ | `auth_full_access` — authenticated |
| `agente_config` | ✅ | `auth_full_access` — authenticated |
| `agente_tarefas` | ✅ | `auth_full_access` — authenticated (migration 0005) |

### Verificação

```sql
select relname, relrowsecurity
from pg_class
where relname like 'agente_%'
order by relname;
-- relrowsecurity = true em todas ✅
```

---

## Notas para o Claude Code

- Criar a migration em `supabase/migrations/0001_initial_schema.sql`.
- O trigger de `atualizado_em` pode ser adicionado depois; por agora actualizar manualmente no backend.
- Não criar tabelas extra sem actualizar este documento primeiro.
