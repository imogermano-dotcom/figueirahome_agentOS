-- ════════════════════════════════════════════════
-- Migration 0035 — nudge dentro da janela de 24h (Matilde)
-- ════════════════════════════════════════════════
-- Carimbo do fluxo, não o estado (mesmo raciocínio da `follow_up_em`, 0030):
-- o painel não edita conversas, mas mesmo assim o carimbo garante um nudge
-- por conversa, uma só vez, sem depender de reler o histórico para saber se
-- já se mandou. Ver docs/fases/matilde-followup-plano.md.

alter table agente_conversas add column nudge_em timestamptz;
