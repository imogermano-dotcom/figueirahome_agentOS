-- ════════════════════════════════════════════════
-- Migration 0020 — Landing pages por imóvel (projecto UNIFICADO, supabase_imoveis)
-- ════════════════════════════════════════════════
-- Páginas de destino geradas por IA para usar como criativo de anúncio
-- (Meta Ads, WhatsApp). Uma linha por imóvel; o conteúdo é escrito uma vez e
-- guardado, não gerado a cada visita.

create table if not exists landing_pages (
  imovel_ref     text primary key references imoveis(imovel_ref) on delete cascade,
  slug           text unique not null,                -- 'fh2450-moradia-t3-buarcos'
  conteudo       jsonb not null default '{}'::jsonb,  -- secções escritas pela IA
  extras         jsonb not null default '{}'::jsonb,  -- video_url, mapa_url, notas (form do painel)
  mostrar_preco  boolean not null default true,       -- imóvel como chamariz (false) ou qualificador (true)
  fonte_hash     text,                                -- sha256 dos dados-fonte; regenera só se mudar
  gerado_em      timestamptz,
  modelo         text,
  custo_usd      numeric(10, 6),
  tokens_input   integer,
  tokens_output  integer,
  criado_em      timestamptz default now(),
  atualizado_em  timestamptz default now()
);

-- NÃO há coluna de estado (activa/vendida/removida) de propósito: `publicado`
-- (GENERATED STORED, migration 0008) já é a verdade sobre se o imóvel ainda
-- está no ar, e a página lê-a a cada visita. Uma segunda coluna só criava mais
-- uma coisa para ficar dessincronizada. Remoção definitiva = DELETE manual.

create index if not exists idx_landing_pages_slug on landing_pages(slug);

alter table landing_pages enable row level security;

-- Backend usa service_role (bypass). Esta política é para o painel autenticado.
-- `anon` fica bloqueado: as páginas públicas passam pelo backend, nunca por
-- PostgREST directo — é o backend que filtra as colunas que podem sair.
drop policy if exists "auth_full_access" on landing_pages;
create policy "auth_full_access" on landing_pages
  for all to authenticated using (true) with check (true);

-- ──────────────────────────────────────────────
-- Gate de qualificação — 4 campos, um dos quais novo na base
-- ──────────────────────────────────────────────
-- O gate recolhe o prazo de compra ('Até 3 meses' | '3 a 6 meses' |
-- 'Mais de 6 meses' | 'Só a pesquisar' — `api/landing.py::PRAZOS`). Fecha a
-- lacuna registada no CLAUDE.md: "MQL = orçamento + zona + tipo de interesse.
-- O timing não é recolhido."
alter table agente_clientes add column if not exists prazo_compra text;

-- `agente_leads.imovel_id` é uuid e está sempre null na prática (a chave de
-- negócio de `imoveis` é `imovel_ref` text, não um uuid). A lead que vem de uma
-- landing page sabe sempre de que imóvel veio — sem isto, perdia-se.
alter table agente_leads add column if not exists imovel_ref text;
create index if not exists idx_agente_leads_imovel_ref on agente_leads(imovel_ref);

-- VERIFICAÇÃO (executar após aplicar):
-- select column_name, data_type from information_schema.columns
--   where table_name = 'landing_pages' order by ordinal_position;
-- select column_name from information_schema.columns
--   where table_name = 'agente_clientes' and column_name = 'prazo_compra';
-- select column_name from information_schema.columns
--   where table_name = 'agente_leads' and column_name = 'imovel_ref';
