# Resumo — nudge generalizado (Inês/Bárbara) + janela 2h (25/09)

Plano: `.claude/plans/shimmying-bubbling-pearl.md` (ver histórico da sessão).
Pedido: mesmo lembrete dentro da conversa que já existia só para a Matilde
(A1, `matilde-followup-resumo.md`, 09/09), agora também para a Inês (A3) e a
Bárbara (A4); janela mínima 6h → 2h.

## O que mudou

`backend/app/agents/broker/nudge.py`:
- `_JANELA_MIN_HORAS`: `6` → `2` (global, os 3 agentes).
- `_candidatos(agente, guarda)` e `enviar_nudges(agente)` parametrizados —
  deixaram de estar hardcoded a `"a1_vendedor"`.
- `_AGENTES` — config central por assistente (texto, `log_tipo` do
  `agente_sync_log`, guarda opcional), mesmo padrão "um motor, N
  assistentes" do resto do broker.
- `enviar_todos_nudges()` — nova, corre os 3 e agrega os resumos.
- `backend/app/api/nudge.py` — `/api/matilde/nudge` (nome mantido por causa
  do cron já registado, mudar o `name` em `crons/schedules.json` apaga o
  histórico de execuções) passa a chamar `enviar_todos_nudges()`.
- `backend/tests/test_nudge.py` — testes existentes ajustados à nova
  assinatura + 2 novos (A3/A4 sem guarda, agregação dos 3). Suite: 276
  verdes (era 274).

## Decisão: sem guarda de "fechada" para A3/A4

`_pode_enviar` (agora `_pode_enviar_a1`) consulta `leads.estado`/
`ESTADOS_FECHADOS` — específico do fluxo de compra. Para A3/A4 não existe
equivalente: confirmei ao vivo (PostgREST) que `contactos.estado` só tem o
valor `'nova'` (ou `null`) em todas as linhas com `tipo_contacto`
preenchido — nada no código escreve lá um estado fechado. Construir uma
guarda que nunca dispara seria código morto. A3/A4 ficam só com a detecção
de despedida (já genérica) como travão. Limitação conhecida, documentada no
código (`nudge.py`, comentário acima de `_AGENTES`).

## Textos (não são templates Meta — texto livre dentro de conversa aberta)

- Inês (A3): *"Ainda tem interesse em avançar com a candidatura? Fico a
  postos para continuar, ou diga-me só que não para eu não voltar a
  incomodar."*
- Bárbara (A4): *"Ainda tem interesse em avançar com a venda do seu imóvel?
  Fico a postos para continuar, ou diga-me só que não para eu não voltar a
  incomodar."*

## Por fazer

- Deploy (confirmação explícita).
- Confirmar ao vivo: `/api/matilde/nudge` devolve as 3 chaves
  (`a1_vendedor`/`a3_recrutamento`/`a4_angariador`); `agente_sync_log` grava
  3 registos por corrida (`nudge_matilde`/`nudge_ines`/`nudge_barbara`).
- Sem migration — `agente_conversas.nudge_em` já é genérica.
