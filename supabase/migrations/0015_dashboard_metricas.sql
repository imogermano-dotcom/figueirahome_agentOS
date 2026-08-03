-- ════════════════════════════════════════════════
-- Migration 0015 — RPC dashboard_metricas (projecto SECUNDÁRIO, supabase_imoveis)
-- ════════════════════════════════════════════════
-- Uma função, um round-trip. O endpoint /api/dashboard fazia 5 queries em série
-- sobre as tabelas do agente (1 a 5 linhas cada) e ignorava o negócio real:
-- 25 mil oportunidades, 27 mil contactos, 4462 imóveis.
--
-- Contar isto do lado do cliente não é opção — agregação fica no Postgres.
-- `stable`: só lê. Sem `security definer` — o backend usa service_role_key.
--
-- Valores de referência no momento de escrever (2026-08-03), para conferir:
--   oportunidades 25301 = Ativa 21991 + Ganha 872 + Perdida 2438
--   imoveis 4462, publicados 53, Disponível 67  <- a diferença é intencional,
--   `publicado` (GENERATED, migration 0008) é o que está mesmo no site.

create or replace function dashboard_metricas()
returns jsonb
language sql
stable
as $$
with
-- Top 8 responsáveis; a cauda longa colapsa em "Outros" para não gerar
-- 13 barras ilegíveis (a skill de dataviz corta em ~7 classes).
resp as (
  select coalesce(nullif(trim(responsavel), ''), 'Sem responsável') as nome,
         count(*) as total
  from oportunidades
  group by 1
),
resp_rank as (
  select nome, total, row_number() over (order by total desc) as pos
  from resp
),
-- O `group by` final não é decorativo: os dados têm mesmo uma categoria
-- chamada "Outros", que colidia com este balde da cauda e produzia duas
-- linhas com o mesmo nome (chave duplicada no React, barra a duplicar).
-- Somar as duas é o comportamento correcto.
resp_final as (
  select nome, sum(total) as total from (
    select nome, total from resp_rank where pos <= 8
    union all
    select 'Outros', sum(total) from resp_rank where pos > 8
  ) t group by nome
),
orig as (
  select coalesce(nullif(trim(origem), ''), 'Sem origem') as nome,
         count(*) as total
  from oportunidades
  group by 1
),
orig_rank as (
  select nome, total, row_number() over (order by total desc) as pos
  from orig
),
orig_final as (
  select nome, sum(total) as total from (
    select nome, total from orig_rank where pos <= 7
    union all
    select 'Outros', sum(total) from orig_rank where pos > 7
  ) t group by nome
),
-- Uma linha por tipo de sync: a mais recente.
sync as (
  select distinct on (tipo) tipo, executado_em, resumo
  from agente_sync_log
  order by tipo, executado_em desc
)
select jsonb_build_object(

  'oportunidades', (
    select jsonb_build_object(
      'total',    count(*),
      'ativas',   count(*) filter (where oportunidade_estado = 'Ativa'),
      'ganhas',   count(*) filter (where oportunidade_estado = 'Ganha'),
      'perdidas', count(*) filter (where oportunidade_estado = 'Perdida'),
      'venda',       count(*) filter (where tipo_oportunidade = 'Venda'),
      'angariacao',  count(*) filter (where tipo_oportunidade = 'Angariação'),
      'arrendamento',count(*) filter (where tipo_oportunidade = 'Arrendamento'))
    from oportunidades),

  'por_responsavel', (
    select coalesce(jsonb_agg(jsonb_build_object('nome', nome, 'total', total)
                              order by total desc), '[]'::jsonb)
    from resp_final where total > 0),

  'por_origem', (
    select coalesce(jsonb_agg(jsonb_build_object('nome', nome, 'total', total)
                              order by total desc), '[]'::jsonb)
    from orig_final where total > 0),

  'imoveis', (
    select jsonb_build_object(
      'total',       count(*),
      -- `publicado` é a verdade do site, não `disponibilidade`.
      'publicados',  count(*) filter (where publicado),
      'disponiveis', count(*) filter (where disponibilidade = 'Disponível'),
      'prospeccao',  count(*) filter (where disponibilidade = 'Em Prospecção'),
      'por_validar', count(*) filter (where disponibilidade = 'Por validar'),
      'retirados',   count(*) filter (where disponibilidade = 'Retirado'))
    from imoveis),

  'contactos', (select count(*) from contactos),

  'assistentes', (
    select jsonb_build_object(
      'conversas_total', (select count(*) from agente_conversas),
      'conversas_por_agente', (
        select coalesce(jsonb_agg(jsonb_build_object('nome', a, 'total', n)
                                  order by n desc), '[]'::jsonb)
        from (select coalesce(agente, 'sem router') as a, count(*) as n
              from agente_conversas group by 1) x),
      'visitas_pendentes', (
        select count(*) from agente_tarefas
        where estado = 'pendente' and titulo ilike 'Visita %'),
      'escalar_pendentes', (
        select count(*) from agente_tarefas
        where estado = 'pendente' and titulo ilike '%ESCALAR —%'),
      'tarefas_pendentes', (
        select count(*) from agente_tarefas where estado = 'pendente'),
      'clientes', (select count(*) from agente_clientes))),

  'sync', (
    select coalesce(jsonb_agg(jsonb_build_object(
             'tipo', tipo, 'executado_em', executado_em, 'resumo', resumo)
           order by executado_em desc), '[]'::jsonb)
    from sync),

  -- Dados incompletos que ninguém vê hoje. Postos à vista de propósito:
  -- os imóveis `fonte='manual'`/`Em Prospecção` são o bloqueador registado
  -- no CLAUDE.md, e as oportunidades sem data são a razão de não haver
  -- gráfico de evolução neste dashboard.
  'alertas', jsonb_build_object(
    'imoveis_fonte_manual',   (select count(*) from imoveis where fonte = 'manual'),
    'imoveis_prospeccao',     (select count(*) from imoveis where disponibilidade = 'Em Prospecção'),
    'oport_sem_etapa',        (select count(*) from oportunidades
                               where etapa_atual is null or trim(etapa_atual) = ''),
    'oport_sem_responsavel',  (select count(*) from oportunidades
                               where responsavel is null or trim(responsavel) = ''),
    'oport_sem_data',         (select count(*) from oportunidades
                               where data_criacao_iso is null))
);
$$;

comment on function dashboard_metricas() is
  'Todas as métricas do dashboard num único jsonb. Ver docs/fases/dashboard-plano.md.';
