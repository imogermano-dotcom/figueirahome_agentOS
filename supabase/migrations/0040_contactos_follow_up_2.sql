-- ════════════════════════════════════════════════
-- Migration 0040 — `contactos` ganha `follow_up_2_em`
-- ════════════════════════════════════════════════
-- Aditivo, mesmo padrão de `respondeu_em`/`follow_up_em` (migration 0039).
--
-- Travão de "só uma vez" do 3º toque de recrutamento (72h desde o 1º
-- template, âncora independente do follow-up de 24h — decisão do
-- utilizador, 22/09). `template_enviado_em` fica imutável desde a 0039 (o
-- fluxo de 24h deixou de o reescrever) precisamente para os dois follow-ups
-- poderem medir a partir do mesmo ponto de origem.

alter table contactos
  add column follow_up_2_em timestamptz;

comment on column contactos.follow_up_2_em is
  'Quando o fluxo n8n de follow-up de recrutamento a 72h mandou a 3ª mensagem (última tentativa). Travão de "só uma vez", independente de follow_up_em.';
