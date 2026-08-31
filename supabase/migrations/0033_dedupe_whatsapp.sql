-- ════════════════════════════════════════════════
-- Migration 0033 — dedupe de mensagens WhatsApp (projecto UNIFICADO)
-- ════════════════════════════════════════════════
-- O webhook do WhatsApp extraía o `message_id` (wamid da Meta) só para marcar
-- como lida — nunca verificava se já o tinha processado. Uma reentrega do
-- mesmo webhook (a Meta garante "at least once", reenvia por timeout ou falha
-- transitória) reprocessava a mensagem do zero: o Claude respondia outra vez,
-- chamava as mesmas tools outra vez.
--
-- Achado a 2026-08-31 a investigar tarefas duplicadas no painel: visitas do
-- mesmo cliente/imóvel/hora, sempre 30-65 segundos de diferença entre as
-- cópias — típico de reentrega de webhook, não de reconfirmação humana. Uma
-- lead ("João Marques") foi promovida a qualificada duas vezes por este
-- mesmo mecanismo.
--
-- `INSERT ... ON CONFLICT DO NOTHING`, não "SELECT depois INSERT": entre ler
-- e escrever há uma janela onde duas reentregas quase simultâneas passam as
-- duas. A restrição UNIQUE torna a verificação atómica.

create table if not exists agente_mensagens_processadas (
  message_id text primary key,
  criado_em  timestamptz not null default now()
);

comment on table agente_mensagens_processadas is
  'Dedupe de wamids do WhatsApp. Uma linha = uma mensagem já processada; reentregas da Meta batem no UNIQUE e são ignoradas. Sem TTL de propósito: o volume é baixo e apagar abre a porta a reprocessar uma reentrega tardia.';

-- ── RLS ──────────────────────────────────────────────────────────────────
-- Mesmo padrão da 0023: backend usa `service_role`, que bypassa; `anon` fica
-- de fora.
alter table agente_mensagens_processadas enable row level security;

drop policy if exists "auth_full_access" on agente_mensagens_processadas;
create policy "auth_full_access" on agente_mensagens_processadas
  for all to authenticated using (true) with check (true);

-- ── VERIFICAÇÃO ──────────────────────────────────────────────────────────
-- select count(*) from agente_mensagens_processadas;  -- esperado: 0 (tabela nova)
