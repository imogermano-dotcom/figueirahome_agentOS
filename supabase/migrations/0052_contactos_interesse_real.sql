-- ════════════════════════════════════════════════
-- Migration 0052 — `contactos`: interesse real marcado pelo assistente
-- ════════════════════════════════════════════════
-- Plano: docs/fases/lead-interesse-real-ego-plano.md (25/10, pedido #17 do Miguel).
--
-- Quem responde à Matilde com interesse real (pede visita, negoceia o preço, fica qualificado) não chegava ao
-- eGO: só havia tarefa e email. Agora o assistente MARCA o contacto e o cron `leads-compra-para-ego` cria a lead
-- (9h–20h de Lisboa, sem duplicar), como já faz com quem não responde. A conversa nunca fala com o eGO.
--
--   interesse_real_em      quando o 1.º sinal chegou. Não-nulo e `ego_lead_em` nulo = por criar no eGO.
--   interesse_real_motivo  o que o originou: 'visita', 'qualificada' ou o motivo da escalada ('negociação de preço'...).
--   interesse_real_resumo  resumo da conversa para o OBS da lead no eGO. Sinais seguintes, antes de a lead ser
--                          criada, acrescentam-se ao texto.
--
-- Escritores: `leads_para_ego.marcar_interesse_real` (backend, tools do assistente), UPDATE por `id`. Aditiva e
-- nullable (mesmo padrão da 0044/0045/0047/0048/0050): o scraper, o pipeline do Miguel e as RPCs da Meta não as
-- tocam. Sem backfill (decisão de 25/10: só daqui em diante).

alter table public.contactos add column if not exists interesse_real_em timestamptz;
alter table public.contactos add column if not exists interesse_real_motivo text;
alter table public.contactos add column if not exists interesse_real_resumo text;

comment on column public.contactos.interesse_real_em is
  'Quando o assistente confirmou interesse real (visita, negociação, lead qualificada). Não-nulo com ego_lead_em nulo = o cron cria a lead no eGO.';
comment on column public.contactos.interesse_real_motivo is
  'Origem do sinal de interesse real: visita, qualificada ou o motivo da escalada.';
comment on column public.contactos.interesse_real_resumo is
  'Resumo da conversa para o campo de observações da lead no eGO.';

notify pgrst, 'reload schema';

-- ── VERIFICAÇÃO ──────────────────────────────────────────────────────────
-- select count(*) filter (where interesse_real_em is not null) from public.contactos;   -- esperado: 0

-- Desfazer (se preciso):
--   alter table public.contactos drop column if exists interesse_real_resumo;
--   alter table public.contactos drop column if exists interesse_real_motivo;
--   alter table public.contactos drop column if exists interesse_real_em;
