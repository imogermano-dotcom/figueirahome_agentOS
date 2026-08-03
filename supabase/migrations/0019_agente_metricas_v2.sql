-- ════════════════════════════════════════════════
-- Migration 0019 — agente_metricas v2, em 4 blocos (projecto SECUNDÁRIO)
-- ════════════════════════════════════════════════
-- Substitui a versão da 0017. Mesma assinatura, resposta reorganizada em
-- funil / atendimento / preferencias / operacional.
-- Depende das colunas da 0018 — aplicar 0018 primeiro.
--
-- CREATE OR REPLACE FUNCTION apenas. Reversível reaplicando a 0017.
--
-- MQL = orçamento + zona + tipo de interesse (decisão do utilizador,
-- 2026-08-03). O "timing" não é recolhido pelo A1 e não entra no critério.

create or replace function agente_metricas(
  p_agente text default null,
  p_dias   integer default 30
)
returns jsonb
language sql
stable
as $$
with
janela as (select now() - make_interval(days => greatest(p_dias, 1)) as desde),

base as (   -- turnos
  select i.* from agente_interacoes i, janela j
  where i.criado_em >= j.desde
    and (p_agente is null or i.agente = p_agente)
),

convs as (
  select c.*, coalesce(jsonb_array_length(c.mensagens), 0) as n_mensagens
  from agente_conversas c, janela j
  where c.atualizado_em >= j.desde
    and (p_agente is null or c.agente = p_agente)
),

-- Clientes captados pelos assistentes. `origem` é o canal ('whatsapp'/'web'),
-- posto por find_or_create_cliente — distingue-os dos importados do CRM.
clientes as (
  select cl.* from agente_clientes cl, janela j
  where cl.criado_em >= j.desde
    and cl.origem in ('whatsapp', 'web', 'chamada')
),

tarefas as (
  select t.* from agente_tarefas t, janela j
  where t.criado_em >= j.desde
    and t.tipo is not null                       -- só as criadas pelos assistentes
    and (p_agente is null or t.agente = p_agente or t.agente is null)
),

-- Argumentos das pesquisas. Uma linha por chamada a pesquisar_imoveis.
pesquisas as (
  select d->'input' as input
  from base, jsonb_array_elements(coalesce(base.tools_detalhe, '[]'::jsonb)) as d
  where d->>'nome' = 'pesquisar_imoveis' and d ? 'input'
)

select jsonb_build_object(
  'periodo_dias', greatest(p_dias, 1),
  'agente', p_agente,

  -- ── 🌟 FUNIL E CONVERSÃO ──────────────────────
  'funil', (
    select jsonb_build_object(
      'leads_captados', (select count(*) from clientes),
      -- MQL: orçamento + zona + tipo de interesse, todos preenchidos.
      'mqls', (select count(*) from clientes
               where orcamento is not null
                 and nullif(trim(coalesce(zona_preferida, '')), '') is not null
                 and nullif(trim(coalesce(tipo_interesse, '')), '') is not null),
      'conversas', (select count(*) from convs),
      'visitas_agendadas', (select count(*) from tarefas where tipo = 'visita'),
      'taxa_qualificacao', case
        when (select count(*) from clientes) = 0 then 0
        else (select count(*) from clientes
              where orcamento is not null
                and nullif(trim(coalesce(zona_preferida, '')), '') is not null
                and nullif(trim(coalesce(tipo_interesse, '')), '') is not null)::numeric
             / (select count(*) from clientes) end,
      'taxa_conversao', case
        when (select count(*) from convs) = 0 then 0
        else (select count(*) from tarefas where tipo = 'visita')::numeric
             / (select count(*) from convs) end)),

  -- ── 💬 DESEMPENHO E SAÚDE DO ATENDIMENTO ──────
  'atendimento', (
    select jsonb_build_object(
      'tempo_resposta_p50', coalesce((select percentile_cont(0.5) within group (order by latencia_ms) from base), 0),
      'tempo_resposta_p95', coalesce((select percentile_cont(0.95) within group (order by latencia_ms) from base), 0),
      'transbordos', (select count(*) from tarefas where tipo = 'escalar'),
      'taxa_transbordo', case
        when (select count(*) from convs) = 0 then 0
        else (select count(*) from tarefas where tipo = 'escalar')::numeric
             / (select count(*) from convs) end,
      -- Para que perguntas a IA não chegou: o que treinar a seguir.
      'motivos', (
        select coalesce(jsonb_agg(jsonb_build_object('nome', motivo, 'total', n)
                                  order by n desc), '[]'::jsonb)
        from (select coalesce(nullif(trim(motivo), ''), 'sem motivo') as motivo, count(*) as n
              from tarefas where tipo = 'escalar' group by 1 limit 8) x),
      'mensagens_por_conversa', coalesce((select avg(n_mensagens) from convs), 0),
      'conversas_longas', (select count(*) from convs where n_mensagens >= 8),
      -- Participantes com mais do que uma conversa: voltaram a procurar-nos.
      'clientes_recorrentes', (
        select count(*) from (select participante from convs
                              group by 1 having count(*) > 1) x),
      'iteracoes_media', coalesce((select avg(iteracoes) from base), 0))),

  -- ── 🏠 PREFERÊNCIAS DE MERCADO ────────────────
  -- Vem dos argumentos das pesquisas: capta toda a gente que procurou,
  -- não só quem chegou a ficar registado como cliente.
  'preferencias', (
    select jsonb_build_object(
      'pesquisas', (select count(*) from pesquisas),
      'zonas', (
        select coalesce(jsonb_agg(jsonb_build_object('nome', zona, 'total', n)
                                  order by n desc), '[]'::jsonb)
        from (select initcap(trim(input->>'zona')) as zona, count(*) as n
              from pesquisas where nullif(trim(coalesce(input->>'zona','')), '') is not null
              group by 1 order by n desc limit 8) x),
      'tipologias', (
        select coalesce(jsonb_agg(jsonb_build_object('nome', tipo, 'total', n)
                                  order by n desc), '[]'::jsonb)
        from (select coalesce('T' || (input->>'quartos'), initcap(input->>'natureza')) as tipo,
                     count(*) as n
              from pesquisas
              where input->>'quartos' is not null or input->>'natureza' is not null
              group by 1 order by n desc limit 8) x),
      'preco_medio_pedido', coalesce((
        select avg((input->>'preco_max')::numeric) from pesquisas
        where input->>'preco_max' ~ '^[0-9.]+$'), 0),
      'preco_mediano_pedido', coalesce((
        select percentile_cont(0.5) within group (order by (input->>'preco_max')::numeric)
        from pesquisas where input->>'preco_max' ~ '^[0-9.]+$'), 0),
      'orcamento_medio_declarado', coalesce((
        select avg(orcamento) from clientes where orcamento is not null), 0),
      'intencao', (
        select coalesce(jsonb_agg(jsonb_build_object('nome', tipo, 'total', n)
                                  order by n desc), '[]'::jsonb)
        from (select coalesce(nullif(trim(tipo_interesse), ''), 'não declarado') as tipo,
                     count(*) as n
              from clientes group by 1) x))),

  -- ── ⚙️ ESTADO OPERACIONAL ─────────────────────
  -- Sem uptime: não há sonda a medi-lo. `taxa_sucesso` e `ultima_interacao`
  -- são o que os dados suportam; uptime real vive no painel do Fly.io.
  'operacional', (
    select jsonb_build_object(
      'turnos', count(*),
      'custo_total_usd', coalesce(sum(custo_usd), 0),
      'custo_por_interacao', coalesce(avg(custo_usd), 0),
      'taxa_sucesso', case when count(*) = 0 then 1
                           else 1 - count(*) filter (where erro is not null)::numeric / count(*) end,
      'erros', count(*) filter (where erro is not null),
      'ultima_interacao', max(criado_em),
      'taxa_cache', case
        when coalesce(sum(tokens_input + tokens_cache_read), 0) = 0 then 0
        else sum(tokens_cache_read)::numeric / sum(tokens_input + tokens_cache_read) end,
      'tokens_input', coalesce(sum(tokens_input), 0),
      'tokens_output', coalesce(sum(tokens_output), 0),
      'tokens_cache_read', coalesce(sum(tokens_cache_read), 0),
      'tokens_cache_write', coalesce(sum(tokens_cache_write), 0),
      'contexto_medio', coalesce(avg(tokens_input + tokens_cache_read), 0)::integer,
      'contexto_max', coalesce(max(tokens_input + tokens_cache_read), 0),
      'por_canal', (
        select coalesce(jsonb_agg(jsonb_build_object(
                 'nome', canal, 'total', n, 'custo', custo) order by n desc), '[]'::jsonb)
        from (select canal, count(*) as n, sum(custo_usd) as custo
              from base group by 1) x),
      'tools', (
        select coalesce(jsonb_agg(jsonb_build_object('nome', nome, 'total', n)
                                  order by n desc), '[]'::jsonb)
        from (select t as nome, count(*) as n
              from base, unnest(coalesce(tools_usadas, '{}')) as t
              group by 1) x))
    from base)
);
$$;

comment on function agente_metricas(text, integer) is
  'Métricas por assistente em 4 blocos: funil, atendimento, preferencias, operacional.';
