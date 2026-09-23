-- ════════════════════════════════════════════════
-- Migration 0044 — `contactos` ganha `imovel_ref`
-- ════════════════════════════════════════════════
-- Decisão 23/09: os fluxos de follow-up da Matilde (A1) passam a ler/escrever
-- em `contactos`, não `leads` — mesmo padrão da Inês/Bárbara. `leads` continua
-- a ser a fonte de verdade do 1º template (RPC `lead_meta_compra`, sem
-- alteração), mas `contactos` não tinha `imovel_ref` — o template dos
-- follow-ups precisa dele para o parâmetro `{{2}}`.
--
-- Aditivo, mesmo padrão de `agente`/`id`/`origem`. Sem backfill: o fluxo n8n
-- vai buscar `imovel_ref` a `leads` (por `meta_lead_id`) na 1ª vez que
-- processa cada contacto, e grava aqui como cache — não vale a pena um
-- backfill de uma vez só para uma coluna só lida por um fluxo que ainda não
-- correu.

alter table contactos add column imovel_ref text;

comment on column contactos.imovel_ref is
  'Referência do imóvel do anúncio, para os follow-ups da Matilde citarem qual. Preenchida pelo fluxo n8n a partir de leads.imovel_ref (por meta_lead_id) na 1ª vez, não por trigger.';
