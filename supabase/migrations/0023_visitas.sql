-- ════════════════════════════════════════════════
-- Migration 0023 — `visitas` (projecto UNIFICADO, zphasvfopnbzwnaidsnw)
-- ════════════════════════════════════════════════
-- As visitas do eGO estavam guardadas como colunas `visita_*` DENTRO de
-- `oportunidades`, que tem uma linha por `oportunidade_ref`. O export do Wigo
-- traz uma linha por (oportunidade + nota|tarefa|preferência|visita), por isso
-- um cliente com 5 visitas dá 5 linhas com a MESMA `oportunidade_ref` — e
-- `mapping_todas_colunas.group()` colapsava-as com `setdefault`, ficando só a
-- primeira. As outras 4 eram descartadas antes sequer de chegar à base.
--
-- Medido a 2026-08-14, antes desta migration:
--   25517 oportunidades, 25517 `oportunidade_ref` distintos
--    1739 com visita, 1739 `visita_ref_ego` distintos
--       1 visita por oportunidade, no máximo  ← o tecto era estrutural
--
-- `notas` e `tarefas` nunca sofreram disto: são tabelas próprias com chave
-- composta. As visitas eram o único dos quatro blocos modelado como colunas.
-- Esta migration dá-lhes o mesmo tratamento.
--
-- NÃO mexe em `oportunidades`: `docs/database-schema.md` diz explicitamente
-- para não gerir essa tabela a partir deste repo (é alimentada por um processo
-- do utilizador fora daqui). As colunas `visita_*` ficam como estão e o scraper
-- continua a escrevê-las — quem as lê hoje não parte. Esta tabela é aditiva.

create table if not exists visitas (
  visita_ref_ego             text primary key,   -- 'VF_2886' — id estável do eGO
  oportunidade_ref           text not null,
  visita_imovel_ref          text,               -- o imóvel VISITADO; ≠ oportunidades.imovel_ref
  visita_data                text,               -- texto como no resto do bloco (ver 0011)
  visita_anulada             text,               -- 'Sim'/'Não'; é o que marca a linha como visita
  visita_interessado         text,
  visita_cliente             text,
  visita_imovel_proprietario text,
  visita_pontos_positivos    text,
  visita_pontos_negativos    text,
  visita_sobre_negocio       text,
  visita_observacoes         text,
  visita_responsavel         text,
  criado_em                  timestamptz default now(),
  atualizado_em              timestamptz default now()
);

-- A pergunta que motivou tudo isto foi "quantas visitas teve o FH2571?", e a
-- resposta certa vem por aqui, não por `oportunidades.imovel_ref`.
create index if not exists idx_visitas_imovel on visitas(visita_imovel_ref);
create index if not exists idx_visitas_oportunidade on visitas(oportunidade_ref);

-- ── Backfill do que já existe (as 1739) ──────────────────────────────────
-- Não recupera as visitas perdidas: essas nunca chegaram à base e só voltam
-- reprocessando um export do eGO com período largo (ver docs/decisoes.md).
insert into visitas (
  visita_ref_ego, oportunidade_ref, visita_imovel_ref, visita_data,
  visita_anulada, visita_interessado, visita_cliente, visita_imovel_proprietario,
  visita_pontos_positivos, visita_pontos_negativos, visita_sobre_negocio,
  visita_observacoes, visita_responsavel
)
select
  visita_ref_ego, oportunidade_ref, visita_imovel_ref, visita_data,
  visita_anulada, visita_interessado, visita_cliente, visita_imovel_proprietario,
  visita_pontos_positivos, visita_pontos_negativos, visita_sobre_negocio,
  visita_observacoes, visita_responsavel
from oportunidades
where visita_ref_ego is not null and oportunidade_ref is not null
on conflict (visita_ref_ego) do nothing;

-- ── RLS ──────────────────────────────────────────────────────────────────
-- Mesmo padrão da 0003. Backend e scraper usam `service_role`, que bypassa;
-- `anon` fica de fora. Não repetir aqui o erro das tabelas do eGO, onde uma
-- política chamada "service role full access" apontava a `public` (ver 0022).
alter table visitas enable row level security;

drop policy if exists "auth_full_access" on visitas;
create policy "auth_full_access" on visitas
  for all to authenticated using (true) with check (true);

-- ── VERIFICAÇÃO ──────────────────────────────────────────────────────────
-- select count(*) from visitas;                       -- esperado: 1739
-- select count(*) from visitas where visita_imovel_ref = 'FH2571';  -- 7
