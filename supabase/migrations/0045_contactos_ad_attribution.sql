-- ════════════════════════════════════════════════
-- Migration 0045 — `contactos` ganha atribuição de anúncio Meta
-- ════════════════════════════════════════════════
-- Pedido 28/09: analisar qualidade das leads por anúncio/conjunto de
-- anúncios da Meta. O nó "Meta Lead Info" do n8n (Graph API) já pede
-- ad_id/ad_name/adset_id/adset_name à Meta — só não eram usados. As 3 RPCs
-- (lead_meta_compra/recrutamento/angariacao) passam a receber e gravar
-- estes 4 campos, sempre sobrescritos (mesmo padrão de meta_lead_id/
-- meta_form_name/meta_created_at — a submissão mais recente manda).
--
-- Aditivo. Sem backfill: só a partir de agora o n8n manda estes campos.

alter table contactos
  add column ad_id text,
  add column ad_name text,
  add column adset_id text,
  add column adset_name text;

comment on column contactos.ad_id is
  'ID do anúncio Meta que gerou a lead (RPCs lead_meta_*, campo já pedido pelo n8n à Graph API). Sempre sobrescrito na submissão mais recente.';
comment on column contactos.ad_name is
  'Nome do anúncio Meta que gerou a lead.';
comment on column contactos.adset_id is
  'ID do conjunto de anúncios (adset) Meta que gerou a lead.';
comment on column contactos.adset_name is
  'Nome do conjunto de anúncios (adset) Meta que gerou a lead.';
