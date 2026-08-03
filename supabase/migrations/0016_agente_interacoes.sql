-- ════════════════════════════════════════════════
-- Migration 0016 — agente_interacoes (projecto SECUNDÁRIO, supabase_imoveis)
-- ════════════════════════════════════════════════
-- Observabilidade dos assistentes. Ver docs/fases/assistentes-observabilidade-plano.md.
--
-- CREATE TABLE + 2 índices. Não altera nem lê nenhuma tabela existente.
-- Reversível com: drop table agente_interacoes;
--
-- Porquê uma tabela nova: `agente_conversas` guarda o texto da conversa
-- ({role, content, timestamp}) e mais nada. Tokens, custo, latência, tools
-- chamadas e erros não têm casa — o `engine.py` recebe o `usage` da API em
-- cada resposta e deita-o fora. Sem isto, "gastos com API" é incalculável.
--
-- Uma linha = um turno do assistente (uma mensagem do cliente e a resposta),
-- somando todas as chamadas à API que o loop de tools fez nesse turno.

create table if not exists agente_interacoes (
  id                 uuid primary key default uuid_generate_v4(),
  conversa_id        uuid references agente_conversas(id) on delete cascade,
  agente             text not null,          -- a1_vendedor | a2_geral | broker
  canal              text not null,          -- whatsapp | web
  modelo             text not null,

  -- Tokens tal como a API os devolve em `usage`, somados ao longo das
  -- iterações do loop de tools.
  tokens_input       integer not null default 0,
  tokens_output      integer not null default 0,
  tokens_cache_read  integer not null default 0,   -- ~0,1x do preço de input
  tokens_cache_write integer not null default 0,   -- 1,25x do preço de input

  -- Custo em USD calculado no momento da chamada, com os preços então
  -- vigentes. Guardado e não recalculado de propósito: é o que foi de facto
  -- cobrado. Recalcular a partir dos tokens reescreveria o histórico sempre
  -- que a Anthropic mudasse a tabela de preços.
  custo_usd          numeric(12,8) not null default 0,

  latencia_ms        integer,
  iteracoes          integer not null default 1,   -- voltas no loop de tools
  tools_usadas       text[],                       -- ['pesquisar_imoveis', ...]
  tool_forcada       boolean not null default false,
  erro               text,                         -- null = correu bem
  criado_em          timestamptz not null default now()
);

-- O padrão de leitura do painel: métricas de um assistente num período.
create index if not exists idx_agente_interacoes_agente_data
  on agente_interacoes (agente, criado_em desc);

-- Abrir uma conversa e ver o custo de cada turno.
create index if not exists idx_agente_interacoes_conversa
  on agente_interacoes (conversa_id);

comment on table agente_interacoes is
  'Um turno de assistente = uma linha. Tokens, custo, latência e tools. Ver docs/fases/assistentes-observabilidade-plano.md.';

alter table agente_interacoes enable row level security;

create policy auth_full_access on agente_interacoes
  for all to authenticated using (true) with check (true);
