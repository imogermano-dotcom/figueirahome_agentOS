-- ════════════════════════════════════════════════
-- Migration 0014 — assistentes A1/A2 (projecto SECUNDÁRIO, supabase_imoveis)
-- ════════════════════════════════════════════════
-- Reformulação dos agentes segundo `docs/fases/assistentes-a1-a2-plano.md`.
--
-- Duas alterações, nada mais. A spec (`assistentes-ia-especificacao.md`)
-- propõe as tabelas `ai_conversations`, `ai_messages`, `ai_visit_bookings` e
-- `agency_knowledge` — todas rejeitadas por duplicarem estruturas existentes:
--   ai_conversations  -> agente_conversas + a coluna `agente` abaixo
--   ai_messages       -> agente_conversas.mensagens (jsonb)
--   ai_visit_bookings -> agente_tarefas (já indexada e já visível no painel)
--   agency_knowledge  -> agente_config[a2_geral].instrucoes (editável sem deploy)

-- ── 1. Routing sticky ────────────────────────────
-- `agente_conversas` só discrimina por `canal`. O router precisa de saber
-- que assistente já detém a thread, para não re-decidir a cada mensagem.
-- NULL = linha legada -> o router decide e a partir daí fica colado.
alter table agente_conversas add column if not exists agente text;

comment on column agente_conversas.agente is
  'a1_vendedor | a2_geral | broker — assistente que detém a thread (routing sticky)';

-- ── 2. Linhas de config dos assistentes novos ────
-- `agente_config` já É a tabela de assistentes (agente unique, persona,
-- instrucoes, idioma, ativo). Semear aqui evita ter de transformar o
-- PUT /api/config/{agente} num upsert.
insert into agente_config (agente, persona, instrucoes) values
  (
    'a1_vendedor',
    'Assistente comercial da Figueirahome. Tom profissional e caloroso, PT-PT, frases curtas.',
    'Foca-te na zona da Figueira da Foz e concelhos vizinhos. Menciona o portefólio de moradias quando fizer sentido.'
  ),
  (
    'a2_geral',
    'Recepcionista virtual da Figueirahome. Tom cordial e breve, PT-PT.',
    E'Horário: segunda a sexta, 9h30–18h30. Sábado por marcação.\n'
    'Morada: (preencher no painel).\n'
    'Serviços: mediação de compra e venda, arrendamento, avaliação gratuita, gestão de imóveis.\n'
    'Parceiros de crédito habitação: (preencher no painel).'
  )
on conflict (agente) do nothing;
