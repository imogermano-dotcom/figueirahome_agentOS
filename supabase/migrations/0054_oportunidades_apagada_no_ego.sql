-- ════════════════════════════════════════════════
-- Migration 0054 — `oportunidades`: apagada no eGO
-- ════════════════════════════════════════════════
-- Plano: docs/fases/oportunidades-apagadas-plano.md (pedido #31 do Miguel, 26/10).
--
-- Uma oportunidade apagada no eGO deixa de vir nos relatórios e o sync (só as «editadas nas últimas 48 h») nunca a relê:
-- ficava «Ativa»/«Perdida» para sempre, bloqueava a criação de leads dessa pessoa e entrava nas contagens.
--
--   apagada_no_ego  true quando o eGO a dá como apagada (`GetOpportunity` com fieldStatusId = 1, ou 404). Não apaga nada:
--                   as notas, tarefas e o histórico ficam. Volta a false se o eGO a repuser.
--   apagada_em      quando a marcámos.
--
-- Escritor: `oportunidades_sync.reconciliar_apagadas` (cron das 04:17 UTC), UPDATE por `oportunidade_ref`. Aditiva; o scraper, o pipeline
-- do Miguel e o portal não a tocam (o portal passa a poder filtrar por ela). Sem backfill: a primeira corrida apanha as existentes (90 dias).

alter table public.oportunidades add column if not exists apagada_no_ego boolean not null default false;
alter table public.oportunidades add column if not exists apagada_em timestamptz;

comment on column public.oportunidades.apagada_no_ego is
  'true = apagada no eGO (fieldStatusId 1 ou 404). Não se apaga a linha. Arquivada não é apagada.';
comment on column public.oportunidades.apagada_em is 'Quando o sync marcou a oportunidade como apagada no eGO.';

notify pgrst, 'reload schema';

-- ── VERIFICAÇÃO ──────────────────────────────────────────────────────────
-- select count(*) filter (where apagada_no_ego) from public.oportunidades;   -- esperado: 0 (antes da 1.ª corrida)

-- Desfazer (se preciso):
--   alter table public.oportunidades drop column if exists apagada_em;
--   alter table public.oportunidades drop column if exists apagada_no_ego;
