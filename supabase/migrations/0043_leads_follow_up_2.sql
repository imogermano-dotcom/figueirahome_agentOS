-- ════════════════════════════════════════════════
-- Migration 0043 — `leads` ganha `follow_up_2_em`
-- ════════════════════════════════════════════════
-- Aditivo, mesmo padrão de `contactos.follow_up_2_em` (migration 0040).
--
-- Suporta o 2º toque de follow-up da Matilde (A1), 72h desde o 1º template
-- — âncora independente do de 24h (`follow_up_em`), mesma decisão já
-- tomada para a Inês/Bárbara: quem nunca recebeu o de 24h ainda assim
-- recebe este a 72h, medido sempre a partir de `template_enviado_em`
-- (imutável, nenhum dos dois fluxos o reescreve).

alter table leads
  add column follow_up_2_em timestamptz;

comment on column leads.follow_up_2_em is
  'Quando o fluxo n8n de follow-up da Matilde a 72h mandou a 3ª mensagem (última tentativa). Travão de "só uma vez", independente de follow_up_em.';
