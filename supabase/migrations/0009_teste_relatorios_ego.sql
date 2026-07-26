-- ════════════════════════════════════════════════
-- Migration 0009 — teste_imoveis (staging p/ relatório eGO CRM)
-- ════════════════════════════════════════════════
-- Fase 2 (relatórios): scraper Playwright dispara relatório já gravado no
-- eGO CRM ("jmarques_imoveis_notas") e descarrega o resultado. Mesmos
-- nomes de coluna que `imoveis`, mas TODAS `text` (+ `extra jsonb` p/ o
-- que não corresponder a nenhuma) — é staging p/ inspeccionar valores
-- crus antes de decidir tipos/transformações; nunca falha a escrita por
-- causa de preço com "€"/milhares, datas em formato inesperado, etc.
-- Só para validar o mecanismo end-to-end; NÃO tocar em `imoveis`
-- (produção) enquanto isto for teste.
--
-- `teste_oportunidades` fica para quando chegarmos à 2ª acção (schema
-- depende do que o relatório de Oportunidades trouxer — `agente_leads`
-- é fino demais pra servir de molde).

create table teste_imoveis (
  id                      uuid primary key default uuid_generate_v4(),
  imovel_ref              text,
  natureza                text,
  disponibilidade         text,
  estado                  text,
  fonte                   text,
  titulo                  text,
  descricao               text,
  proprietario            text,
  angariador              text,
  vendedor                text,
  quartos                 text,
  casas_banho             text,
  suites                  text,
  piso                    text,
  num_pisos               text,
  numero                  text,
  fracao                  text,
  area_util               text,
  area_bruta              text,
  area_terreno            text,
  conservacao             text,
  certificacao_energetica text,
  venda_preco             text,
  arrendamento_preco      text,
  comissao_agencia        text,
  comissao_angariador     text,
  comissao_vendedor       text,
  exclusividade           text,
  morada                  text,
  codigo_postal           text,
  concelho                text,
  freguesia               text,
  zona                    text,
  piscina                 text,
  garagem                 text,
  jardim                  text,
  terraco                 text,
  varanda                 text,
  vista_mar               text,
  vista_praia             text,
  ar_condicionado         text,
  elevador                text,
  aquecimento_central     text,
  arrecadacao             text,
  estacionamento          text,
  portais                 text,
  foto_principal          text,
  fotos                   text,
  ego_id                  text,
  ego_atualizado_em       text,
  data_criacao            text,
  data_alteracao          text,
  extra                   jsonb default '{}'::jsonb,  -- colunas do relatório sem correspondência em `imoveis`
  criado_em               timestamptz default now()
);

alter table teste_imoveis enable row level security;
create policy auth_full_access on teste_imoveis for all to authenticated using (true) with check (true);
