-- ════════════════════════════════════════════════
-- Migration 0032 — `leads.contacto_humano_em` (projecto UNIFICADO)
-- ════════════════════════════════════════════════
-- A Matilde não escreve por cima de quem já está a ser tratado por uma pessoa.
--
-- Veio do cruzamento de 2026-08-29: das 45 leads que ficaram por entregar
-- durante o apagão do WhatsApp, **8 já existiam como contacto no eGO** e 4 têm
-- oportunidade ACTIVA com uma consultora. Reenviar-lhes um template automático
-- da Matilde sobre outro imóvel, por cima de um processo a decorrer, é mau — e
-- não havia nenhuma forma de o dizer à base.
--
-- Só uma coluna. A **nota** não precisa de nada novo: `leads.notas` (0021) já
-- existe, já é editável no painel e já aparece na tabela. **Quem** contactou
-- também não: `leads.responsavel` existe desde a 0021 e nunca teve escritor —
-- passa a tê-lo. Aqui só falta o carimbo, que é o que os fluxos consultam.
--
-- Coluna e não `estado`, pela mesma razão da 0030 (`follow_up_em`): o estado é
-- editável no painel E reescrito pelo n8n a cada passo do fluxo. Marcar
-- 'sem_interesse' à mão para travar o envio perde-se no update seguinte, e
-- mente sobre o desfecho — a pessoa pode estar muito interessada, só que com
-- uma pessoa e não com a assistente.
--
-- Escrita pelo painel (`PUT /api/leads/{id}`, a partir da caixa "Contactada por
-- consultora"). Lida pelos fluxos `02` e `03` do n8n, que passam a exigir
-- `contacto_humano_em=is.null`.
--
-- **O `01` NÃO a filtra**, de propósito: dispara sobre uma lead que a Meta
-- acabou de criar, onde ninguém teve tempo de lhe tocar. Uma guarda ali era
-- código morto a fingir-se de segurança.

alter table leads add column if not exists contacto_humano_em timestamptz;

comment on column leads.contacto_humano_em is
  'Quando uma consultora falou com a lead FORA do agente. NULL = ninguém falou. Travão dos fluxos 02/03 do n8n: nenhuma mensagem iniciada por nós sai para quem já está a ser tratado por uma pessoa. Não trava as respostas da Matilde a quem escreve primeiro — ver o comentário desta migration.';

-- Sem índice, pela mesma razão da 0027 e da 0030: são dezenas de linhas, e a
-- coluna aparece sempre ao lado de filtros muito mais selectivos.

-- ────────────────────────────────────────────────
-- O que isto NÃO faz
-- ────────────────────────────────────────────────
-- Não trava a Matilde a RESPONDER. Se a pessoa escrever no WhatsApp, a
-- assistente responde na mesma — travar isso punha o cliente a falar para o
-- vazio. A guarda é só para mensagens que nós iniciamos (template do `02`,
-- follow-up do `03`).
--
-- Não descobre contactos sozinha: só sabe o que alguém escrever. Uma chamada
-- que a consultora não registe continua invisível, tal como está hoje. Isto
-- resolve daqui para a frente; as 8 de 29/08 são preenchidas à mão.

-- ────────────────────────────────────────────────
-- VERIFICAÇÃO
-- ────────────────────────────────────────────────
-- select column_name, data_type from information_schema.columns
--  where table_name = 'leads' and column_name = 'contacto_humano_em';
--
-- Ninguém marcado ainda (esperado: 0):
-- select count(*) from leads where contacto_humano_em is not null;
--
-- Quantas o `02` deixa de apanhar depois de marcares o shortlist:
-- select count(*) from leads
--  where template_enviado_em is null
--    and contacto_humano_em is not null;
