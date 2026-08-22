-- ════════════════════════════════════════════════
-- Migration 0030 — `leads.follow_up_em` (projecto UNIFICADO)
-- ════════════════════════════════════════════════
-- Desfecho "Sem resposta" da spec §2.2: se não houver resposta em 48h, marca a
-- lead e manda um follow-up por template.
--
-- A pergunta "quem não respondeu?" já era respondível com a `0027`:
--
--   select id, nome, telefone from leads
--    where respondeu_em is null
--      and template_enviado_em < now() - interval '48 hours';
--
-- O que falta é o **travão**. Sem registar que o follow-up saiu, um Schedule
-- Trigger diário no n8n reenvia a mesma mensagem à mesma pessoa todos os dias
-- até ela responder ou bloquear o número. `follow_up_em is null` na consulta
-- garante um follow-up por lead, uma só vez.
--
-- Coluna própria e não `estado = 'sem_resposta'` como travão: o estado é
-- editável no painel, e um corretor a reabrir uma lead para 'contactada' fazia
-- o cron mandar segunda mensagem. O carimbo é do fluxo e ninguém lhe mexe.
--
-- Escrita pelo n8n (`docs/n8n/03-follow-up-48h.json`), a seguir ao envio, no
-- mesmo update que põe `estado = 'sem_resposta'`.
--
-- **Os estados novos não precisam de migration**: a `0021` descreve o
-- vocabulário num comentário, não numa CHECK constraint. `sem_resposta` e
-- `engano` entram só em `app/models/lead.py`.

alter table leads add column if not exists follow_up_em timestamptz;

comment on column leads.follow_up_em is
  'Quando saiu o follow-up das 48h. NULL = ainda não saiu. É o travão do cron do n8n: um follow-up por lead, uma só vez. Não usar o estado para isto — o estado é editável no painel.';

-- Sem índice, pela mesma razão da 0027: são dezenas de linhas. Se a tabela
-- crescer uma ordem de grandeza, o candidato é parcial e igual à query do cron:
--   create index on leads (template_enviado_em)
--    where respondeu_em is null and follow_up_em is null;

-- VERIFICAÇÃO
-- select column_name from information_schema.columns
--  where table_name = 'leads' and column_name = 'follow_up_em';
--
-- Quantas leads o primeiro disparo vai apanhar (correr ANTES de ligar o cron):
-- select count(*) from leads
--  where respondeu_em is null and follow_up_em is null
--    and estado in ('nova','contactada')
--    and lower(ficha->>'aceita_whatsapp') like 'sim%'
--    and template_enviado_em < now() - interval '48 hours';
