-- ════════════════════════════════════════════════
-- Migration 0039 — `contactos` ganha `respondeu_em` e `follow_up_em`
-- ════════════════════════════════════════════════
-- Aditivo, mesmo padrão de `agente`/`id` (20-21/09) — corrido à mão pelo
-- utilizador no editor SQL do Supabase (`contactos` não é gerida por este
-- repo, ver docs/decisoes.md).
--
-- Suporta o fallback de routing de recrutamento (`guards.agente_de_lead`,
-- via `contacto_recrutamento_aberto`/`marcar_contacto_respondeu`) e o fluxo
-- n8n de follow-up — mesmo par de colunas que `leads` já tem (migrations
-- 0027 e 0030), agora espelhado para candidatos de recrutamento que só
-- existem em `contactos`, nunca em `leads`.

alter table contactos
  add column respondeu_em timestamptz,
  add column follow_up_em timestamptz;

comment on column contactos.respondeu_em is
  'Primeira resposta desta pessoa depois do template — escrito por marcar_contacto_respondeu (guards.py). NULL = nunca respondeu.';
comment on column contactos.follow_up_em is
  'Quando o fluxo n8n de follow-up de recrutamento mandou a 2ª mensagem. Travão de "só uma vez" — sem isto o cron diário reenviava.';
