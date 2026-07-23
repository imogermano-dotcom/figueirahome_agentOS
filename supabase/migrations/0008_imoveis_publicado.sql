-- ════════════════════════════════════════════════
-- Migration 0008 — coluna `publicado` em imoveis
-- ════════════════════════════════════════════════
-- Regra de publicação no site (cumulativa, replicada do critério real
-- usado para um imóvel aparecer publicado): disponibilidade exactamente
-- "Disponível" + imovel_ref preenchida (após trim) + preço calculado > 0
-- + ainda devolvido pela última pull completa da Web API pública.
--
-- `disponivel_na_api`: a Web API pública só devolve imóveis publicados,
-- mas quando um imóvel (fonte='egorealestate') desaparece de uma pull
-- completa, `_flag_unpublished` (imoveis_sync.py) NÃO corrige
-- `disponibilidade` — não sabemos o estado real (Retirado/Por validar/
-- Em Prospecção), só o CRM sabe ao certo, e essa correcção só acontece
-- na próxima validação CRM. Sem esta coluna, `publicado` ficaria `true`
-- indevidamente nesse intervalo (disponibilidade ainda diz "Disponível").
-- `disponivel_na_api` é o único facto que a API sync sabe com certeza a
-- cada pull — mantido pela app (sync_egorealestate_api), não GENERATED.
--
-- `publicado` continua GENERATED STORED (Postgres recalcula sempre a
-- partir das colunas da própria linha) — só que agora depende também de
-- `disponivel_na_api`, que é o input que a app actualiza.
--
-- "Preço calculado" = COALESCE(venda_preco, arrendamento_preco) — a Web
-- API do eGO só preenche 1 dos dois por anúncio; ajustar aqui se um dia
-- for preciso outra regra (ex: GREATEST dos dois).

alter table imoveis add column disponivel_na_api boolean not null default true;

alter table imoveis add column publicado boolean generated always as (
  disponibilidade = 'Disponível'
  and length(trim(imovel_ref)) > 0
  and coalesce(venda_preco, arrendamento_preco, 0) > 0
  and disponivel_na_api
) stored;

create index idx_imoveis_publicado on imoveis(publicado);
