-- ════════════════════════════════════════════════
-- Migration 0024 — template enviado à lead (projecto UNIFICADO)
-- ════════════════════════════════════════════════
-- O fluxo real das leads da Meta não passa por nenhum endpoint nosso:
--   Meta → Make (escreve a lead) → webhook → n8n (envia o template) → a lead
--   responde → o A1 assume.
--
-- Sem semeadura, o A1 entra na conversa cego: `engine._perfil_cliente` procura
-- em `agente_clientes`, essa linha não existe ainda, e o assistente pergunta
-- outra vez o orçamento, a zona e o tipo de interesse a quem os acabou de
-- escrever no formulário. As respostas já cá estão, em `leads.ficha` — o que
-- faltava era o texto que já lhe foi enviado, para o A1 não voltar a
-- cumprimentar como se fosse a primeira mensagem.
--
-- `template_enviado_em` é também o único sinal explícito de que o template
-- saiu, e quando. Antes disto não havia nenhum: `estado='contactada'` só era
-- escrito pela semeadura, que este fluxo não usa.
--
-- Escrito pelo n8n, logo a seguir a enviar a mensagem. RLS não muda: a `0021`
-- já activou e a política `to authenticated` cobre as colunas todas.

alter table leads add column if not exists template_enviado    text;
alter table leads add column if not exists template_enviado_em timestamptz;

comment on column leads.template_enviado is
  'Texto do template de WhatsApp enviado pelo n8n. Entra no histórico como mensagem do assistente no primeiro turno (engine._contexto_inicial).';
comment on column leads.template_enviado_em is
  'Quando o template saiu. Único sinal de que a lead foi contactada neste fluxo.';

-- VERIFICAÇÃO
-- select column_name, data_type from information_schema.columns
--  where table_name = 'leads' and column_name like 'template%';
