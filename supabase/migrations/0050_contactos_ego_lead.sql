-- ════════════════════════════════════════════════
-- Migration 0050 — `contactos`: lead criada no eGO pela API
-- ════════════════════════════════════════════════
-- Plano: docs/fases/lead-compra-para-ego-plano.md (16/10).
--
-- Pedido do Miguel: lead de compra da Meta que não responda à Matilde em 2 h passa a ser criada no eGO
-- (`POST /lead/Lead/InsertLead`) para um consultor lhe ligar.
--
--   ego_lead_em  quando o backend tratou a lead (criou-a no eGO, ou viu que a pessoa já tem oportunidade
--                ativa e não criou nada). É o travão: não-nulo = nunca mais se trata.
--   ego_lead_id  id da lead no eGO. NULL com ego_lead_em preenchido = não se criou (já existia) ou a resposta
--                da API não trouxe o id.
--
-- Escritor: `leads_para_ego.processar` (backend, cron), UPDATE por `id`. Aditiva e nullable (mesmo padrão da
-- 0044/0045/0047/0048): o scraper, o pipeline do Miguel e as RPCs da Meta não as tocam. Sem backfill.

alter table public.contactos add column if not exists ego_lead_em timestamptz;
alter table public.contactos add column if not exists ego_lead_id bigint;

comment on column public.contactos.ego_lead_em is
  'Quando o backend tratou esta lead de compra da Meta sem resposta (criou-a no eGO ou saltou por já haver oportunidade ativa). Travão: não-nulo = não repetir.';
comment on column public.contactos.ego_lead_id is
  'Id da lead criada no eGO via API (InsertLead). NULL com ego_lead_em preenchido = não criada.';

notify pgrst, 'reload schema';

-- ── VERIFICAÇÃO ──────────────────────────────────────────────────────────
-- select count(*) filter (where ego_lead_em is not null) from public.contactos;   -- esperado: 0

-- Desfazer (se preciso):
--   alter table public.contactos drop column ego_lead_em, drop column ego_lead_id;
