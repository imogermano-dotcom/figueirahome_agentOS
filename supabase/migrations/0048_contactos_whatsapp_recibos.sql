-- ════════════════════════════════════════════════
-- Migration 0048 — recibos de entrega do WhatsApp em `contactos`
-- ════════════════════════════════════════════════
-- Plano: docs/fases/recibos-whatsapp-plano.md (16/10).
--
-- `200 accepted` da Graph API não é entrega: o n8n marca `template_enviado_em`/`follow_up_em` com o 200
-- (durante 6 dias marcou 45 leads como contactadas que nunca receberam nada). A Meta diz a verdade no
-- webhook (`statuses`), que até aqui só ia para um log de ~30 min. Passa a gravar-se no contacto:
--
--   whatsapp_entregue_em  último 'delivered'/'read' para este número
--   whatsapp_falhou_em    último 'failed' PERMANENTE (código 131026: sem WhatsApp, número inativo,
--                         termos por aceitar — a Meta não distingue)
--   whatsapp_erro_codigo  o código dessa falha
--
-- Escritor: o webhook do WhatsApp (backend), por UPDATE linha a linha. A marca limpa-se quando uma
-- mensagem é entregue depois da falha ou quando a pessoa nos escreve.
--
-- Aditiva e nullable (mesmo padrão da 0044/0045/0047): o scraper, o pipeline do Miguel e as RPCs da
-- Meta não as incluem nos seus payloads e não as tocam. Sem backfill: o histórico anterior não existe.
-- Sem índice: o UPDATE e o resumo diário filtram por telefone/data em poucas linhas.
--
-- O que esta migration NÃO faz: não bloqueia envios (o n8n só passa a filtrar na fase 2).

alter table public.contactos add column if not exists whatsapp_entregue_em timestamptz;
alter table public.contactos add column if not exists whatsapp_falhou_em   timestamptz;
alter table public.contactos add column if not exists whatsapp_erro_codigo integer;

comment on column public.contactos.whatsapp_entregue_em is
  'Último recibo delivered/read da Meta para este número (webhook do WhatsApp). NULL = nunca confirmado.';
comment on column public.contactos.whatsapp_falhou_em is
  'Último failed PERMANENTE da Meta (131026: número sem WhatsApp/inativo). NULL = sem falha conhecida. Limpa-se se a pessoa escrever ou se uma mensagem for entregue depois.';
comment on column public.contactos.whatsapp_erro_codigo is
  'Código de erro da Meta que originou whatsapp_falhou_em.';

notify pgrst, 'reload schema';

-- ── VERIFICAÇÃO ──────────────────────────────────────────────────────────
-- select count(*) filter (where whatsapp_entregue_em is not null) as entregues,
--        count(*) filter (where whatsapp_falhou_em   is not null) as falhas
--   from public.contactos;   -- esperado: 0 e 0 (colunas novas)

-- Desfazer (se preciso):
--   alter table public.contactos drop column whatsapp_entregue_em, drop column whatsapp_falhou_em,
--                                drop column whatsapp_erro_codigo;
