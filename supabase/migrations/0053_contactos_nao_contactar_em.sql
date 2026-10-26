-- ════════════════════════════════════════════════
-- Migration 0053 — `contactos`: a pessoa recusou, nenhum envio automático lhe escreve
-- ════════════════════════════════════════════════
-- Pedido #49 do Miguel (25/10): a Bárbara recebeu um nudge duas horas depois de a pessoa dizer "não estou interessada".
-- O `encerrar_lead` só escrevia em `leads` e os contactos de angariação e recrutamento vivem só em `contactos`:
-- ficava tudo `nova` e nada registava a recusa.
--
--   nao_contactar_em  quando a pessoa recusou (encerrar_lead: engano, sem_interesse ou pausa; ou frase explícita
--                     de opt-out: "não me contactem", "deixem de", "stop"). Não-nulo = nenhum envio PROATIVO
--                     (nudge, follow-ups, cascata, reativação) lhe escreve. Responder a uma mensagem que ela mande
--                     continua a ser normal: a marca bloqueia o que partiu de nós, não a conversa.
--
-- Coluna e não o `estado`, tal como `follow_up_em` e `contacto_humano_em` (0030, 0032): o estado é editável no painel
-- e reescrito pelo n8n. Escritores: `guards.marcar_nao_contactar` (backend), UPDATE por telefone. Leitores: o nudge.
-- Aditiva e nullable; sem backfill (a recusa de antes de 26/10 fica no estado de `leads`, onde já existia).

alter table public.contactos add column if not exists nao_contactar_em timestamptz;

comment on column public.contactos.nao_contactar_em is
  'Quando a pessoa recusou (encerrar_lead ou opt-out explícito). Não-nulo = nenhum envio proativo (nudge, follow-ups, cascata, reativação) lhe escreve.';

notify pgrst, 'reload schema';

-- ── VERIFICAÇÃO ──────────────────────────────────────────────────────────
-- select count(*) filter (where nao_contactar_em is not null) from public.contactos;   -- esperado: 0

-- Desfazer (se preciso):
--   alter table public.contactos drop column if exists nao_contactar_em;
