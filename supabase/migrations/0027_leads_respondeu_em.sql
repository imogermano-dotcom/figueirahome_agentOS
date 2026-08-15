-- ════════════════════════════════════════════════
-- Migration 0027 — `leads.respondeu_em` (projecto UNIFICADO)
-- ════════════════════════════════════════════════
-- Nada marcava que a lead tinha respondido.
--
-- O `conversa_id` só era escrito pela semeadura (`api/leads_meta.py`), que este
-- fluxo não usa; o motor cria a thread em `agente_conversas` mas não a ligava
-- de volta à lead. E `promover_se_qualificada` só mexe no `estado` quando o MQL
-- fica completo.
--
-- Resultado: uma lead que responde mas não qualifica ficava `contactada` —
-- **indistinguível de uma que nunca respondeu**. Qualquer follow-up às 48h
-- mandava segunda mensagem a quem já estava a falar com o A1.
--
-- Coluna própria e não `conversa_id is null`: a semeadura escreve `conversa_id`
-- **antes** de a pessoa dizer nada, e o endpoint continua no repositório. Se um
-- dia voltar a ser usado, a pergunta "respondeu?" passava a dar a resposta
-- errada em silêncio. `respondeu_em` só é escrita quando há mesmo um turno.
--
-- Escrita por `guards.marcar_lead_respondeu`, uma vez só (a query filtra por
-- `respondeu_em is null`, portanto guarda o **primeiro** turno, não o último).

alter table leads add column if not exists respondeu_em timestamptz;

comment on column leads.respondeu_em is
  'Quando a lead respondeu pela primeira vez. NULL = ainda não falou. É este o sinal para o follow-up, não `conversa_id`.';

-- Sem índice de propósito: são 42 linhas. Se a tabela crescer uma ordem de
-- grandeza, o candidato é parcial e igual à query do follow-up:
--   create index on leads (template_enviado_em) where respondeu_em is null;

-- VERIFICAÇÃO
-- select column_name from information_schema.columns
--  where table_name = 'leads' and column_name = 'respondeu_em';
--
-- A query do follow-up passa a ser:
-- select id, nome, telefone from leads
--  where respondeu_em is null
--    and template_enviado_em < now() - interval '48 hours';
