-- ════════════════════════════════════════════════
-- Migration 0017 — RPC agente_metricas (projecto SECUNDÁRIO, supabase_imoveis)
-- ════════════════════════════════════════════════
-- Métricas por assistente a partir de `agente_interacoes` (migration 0016).
-- Mesmo padrão da `dashboard_metricas` (0015), que já provou funcionar:
-- agregação no Postgres, um round-trip, `stable` (só lê).
--
-- CREATE FUNCTION apenas. Reversível com:
--   drop function agente_metricas(text, integer);

create or replace function agente_metricas(
  p_agente text default null,     -- null = todos os assistentes
  p_dias   integer default 30
)
returns jsonb
language sql
stable
as $$
with base as (
  select *
  from agente_interacoes
  where criado_em >= now() - make_interval(days => greatest(p_dias, 1))
    and (p_agente is null or agente = p_agente)
),
por_tool as (
  -- `tools_usadas` é text[]; unnest dá uma linha por chamada de tool.
  select t as nome, count(*) as total
  from base, unnest(coalesce(tools_usadas, '{}')) as t
  group by 1
)
select jsonb_build_object(

  'periodo_dias', greatest(p_dias, 1),
  'agente', p_agente,

  'custos', (
    select jsonb_build_object(
      'total_usd',      coalesce(sum(custo_usd), 0),
      'media_por_turno',coalesce(avg(custo_usd), 0),
      'por_agente', (
        select coalesce(jsonb_agg(jsonb_build_object('nome', agente, 'total', total)
                                  order by total desc), '[]'::jsonb)
        from (select agente, sum(custo_usd) as total from base group by 1) x),
      'por_canal', (
        select coalesce(jsonb_agg(jsonb_build_object('nome', canal, 'total', total)
                                  order by total desc), '[]'::jsonb)
        from (select canal, sum(custo_usd) as total from base group by 1) x))
    from base),

  'volume', (
    select jsonb_build_object(
      'turnos',    count(*),
      'conversas', count(distinct conversa_id),
      'turnos_por_conversa', case
        when count(distinct conversa_id) = 0 then 0
        else count(*)::numeric / count(distinct conversa_id) end)
    from base),

  'desempenho', (
    select jsonb_build_object(
      'latencia_p50', coalesce(percentile_cont(0.5) within group (order by latencia_ms), 0),
      'latencia_p95', coalesce(percentile_cont(0.95) within group (order by latencia_ms), 0),
      'latencia_max', coalesce(max(latencia_ms), 0),
      'iteracoes_media', coalesce(avg(iteracoes), 0),
      'erros', count(*) filter (where erro is not null),
      'taxa_erro', case when count(*) = 0 then 0
                        else count(*) filter (where erro is not null)::numeric / count(*) end)
    from base),

  -- A métrica que diz se o prompt caching está mesmo a funcionar: a fatia
  -- dos tokens de entrada servida do cache, que custa 10% do preço normal.
  -- Se `taxa_cache` vier a zero com volume, o caching está partido.
  'eficiencia', (
    select jsonb_build_object(
      'tokens_input',       coalesce(sum(tokens_input), 0),
      'tokens_output',      coalesce(sum(tokens_output), 0),
      'tokens_cache_read',  coalesce(sum(tokens_cache_read), 0),
      'tokens_cache_write', coalesce(sum(tokens_cache_write), 0),
      'taxa_cache', case
        when coalesce(sum(tokens_input + tokens_cache_read), 0) = 0 then 0
        else sum(tokens_cache_read)::numeric / sum(tokens_input + tokens_cache_read) end)
    from base),

  'tools', (
    select coalesce(jsonb_agg(jsonb_build_object('nome', nome, 'total', total)
                              order by total desc), '[]'::jsonb)
    from por_tool),

  -- Quanto contexto cada turno carrega. Um máximo a subir ao longo do tempo
  -- é o sinal de que as conversas estão a ficar caras.
  'contexto', (
    select jsonb_build_object(
      'input_medio', coalesce(avg(tokens_input + tokens_cache_read), 0)::integer,
      'input_max',   coalesce(max(tokens_input + tokens_cache_read), 0))
    from base),

  -- Acções com efeito no negócio, não só chamadas de tool.
  'accoes', jsonb_build_object(
    'visitas_pendentes', (select count(*) from agente_tarefas
                          where estado = 'pendente' and titulo ilike 'Visita %'),
    'escaladas_pendentes', (select count(*) from agente_tarefas
                            where estado = 'pendente' and titulo ilike '%ESCALAR —%'))
);
$$;

comment on function agente_metricas(text, integer) is
  'Métricas de observabilidade por assistente. Ver docs/fases/assistentes-observabilidade-plano.md.';
