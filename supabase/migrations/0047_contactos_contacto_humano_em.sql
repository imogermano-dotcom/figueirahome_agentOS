-- ════════════════════════════════════════════════
-- Migration 0047 — `contactos.contacto_humano_em`
-- ════════════════════════════════════════════════
-- Decisão 15/10 (`docs/fases/template-compra-contactos-plano.md`): os fluxos de template e de
-- follow-up da Meta passam a ler e a escrever só em `contactos` (compra, angariação e
-- recrutamento). O travão "uma consultora já falou com esta pessoa" vive hoje só em
-- `leads.contacto_humano_em` (0032) — a Angariação e o Recrutamento não têm linha em `leads`,
-- por isso os follow-ups deles nunca o puderam consultar.
--
-- Mesma coluna e mesma semântica da 0032: NULL = ninguém falou; carimbo = uma pessoa falou
-- FORA do agente. É uma coluna e não o estado, pela razão da 0030/0032: o estado é editável e
-- reescrito pelo n8n.
--
-- Aditiva e nullable (mesmo padrão da 0044/0045): o scraper, o pipeline do Miguel e as RPCs da
-- Meta não a incluem nos seus payloads e não a tocam. Sem backfill — medido a 15/10: nenhuma
-- lead tem `contacto_humano_em` preenchido.
--
-- O que esta migration NÃO faz: não há escritor. O painel só marca `leads.contacto_humano_em`
-- (caixa "Contactada por consultora"); até existir um sítio para marcar contactos de
-- angariação/recrutamento, a coluna fica NULL e a guarda é inerte (nunca bloqueia por engano).

alter table public.contactos add column if not exists contacto_humano_em timestamptz;

comment on column public.contactos.contacto_humano_em is
  'Quando uma consultora falou com esta pessoa FORA do agente. NULL = ninguém falou. Travão dos fluxos de template e follow-up do n8n (mesma semântica de leads.contacto_humano_em, 0032).';

notify pgrst, 'reload schema';

-- Desfazer (se preciso): alter table public.contactos drop column contacto_humano_em;
