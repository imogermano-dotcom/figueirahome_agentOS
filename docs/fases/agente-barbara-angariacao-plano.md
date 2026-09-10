# Plano — A4 "Bárbara", assistente de angariação

> Fase nova, pedida pelo utilizador (10/09). Zero código ainda.

## Porquê

A4 (angariação) está na spec (`assistentes-ia-especificacao.md` §6) desde o
início mas foi sempre adiado — `router.py` reconhece as frases e manda-as
para o A2, que só recolhe contacto e escala (`_PROMPT_A2`). O utilizador quer
avançar agora: um assistente próprio, **Bárbara**, para proprietários que
querem vender/arrendar o seu imóvel através da agência.

## Decisão arquitectural (já registada, `docs/decisoes.md:15`)

> "Acrescentar A3/A4 é uma entrada no dict + uma linha em `agente_config`,
> não um ficheiro novo."

Esta fase segue à letra: **mesmo motor (`engine.py`), zero tabelas novas,
zero tools novas.** Bárbara distingue-se de Matilde/Maria só por prompt e
subconjunto de tools — exactamente como o motor já foi desenhado para
suportar.

## Escopo

**Dentro:**
- Registar `a4_angariador` em `assistants.ASSISTENTES` (prompt da Bárbara,
  tools, sem forcing).
- Router: separar o `_ADIADO_RE` actual em dois — recrutamento (continua
  adiado, vai para A2) e angariação (passa a ir para A4).
- `agente_de_lead` (guards.py): mapear `leads.tipo == "angariacao"` → A4,
  espelhando o que já existe para compra/arrendamento → A1. (`models/lead.py`
  já antecipa este eixo no comentário: "compra | angariacao".)
- Seed de `agente_config` para `a4_angariador` (migration nova, à mão como
  todas — `0014` é o precedente).
- Painel: entrada na Sidebar, rota `/agentes/a4_angariador`, `AgenteConfig.jsx`
  (título/ícone/placeholders), opção no `Chat.jsx` para testar sem depender
  do WhatsApp real.
- `_NOME_AGENTE` em `tools.py` — "Bárbara" nos emails de notificação.
- Testes: `test_router.py` actualizado (A3 vs A4 já não são o mesmo caso).

**Fora (deliberado, para não empolar a fase):**
- Tool nova para "visita de avaliação" — reaproveita `escalar_para_humano`
  (mesmo padrão que a A1 já usa para propostas/reclamações). Se em produção
  se vir que precisa de tratamento próprio (like `agendar_visita` tem a regra
  dos 80%), isso é uma fase seguinte, com dados reais a justificá-la.
- Regra de preço/comissão nenhuma em código — não há gate equivalente ao
  "80% do preço" da compra; a Bárbara só qualifica e escala.
- Cross-sell inverso (Bárbara perguntar se o proprietário também quer
  comprar) — a A1 já faz o cross-sell no sentido comprador→vendedor; o
  inverso não foi pedido.
- Nudge 24h — construído só para a A1 (`nudge.py`), não estende a Bárbara
  nesta fase.
- Número de WhatsApp dedicado (a spec sugere um por função) — mantém-se o
  único número existente; o router decide quem responde, como já faz para
  A1/A2.

## Fluxo de conversa da Bárbara (adaptado de §6 da spec)

1. Saudação + identificação como assistente virtual (mesmo padrão A1/A2).
2. Pergunta o essencial em bloco curto: tipo de imóvel, morada/zona, e se já
   está à venda com outra agência ou só particular.
3. Proposta de valor: avaliação gratuita, marketing, rede de compradores,
   suporte jurídico — texto vem de `persona`/`instrucoes` em `agente_config`
   (editável no painel, sem deploy — mesmo mecanismo do A2).
4. Propõe visita de avaliação **sem compromisso** — dois horários concretos,
   como a A1 já faz em `agendar_visita` (mesma UX, sem o gate de preço).
5. Regista com `guardar_dados_cliente` (`tipo_interesse="venda"`) e escala
   com `escalar_para_humano` (`motivo="visita de avaliação"`) — cria a tarefa
   e o email ao corretor, tal como a A1 já faz para propostas.
6. Engano/desistência → `encerrar_lead`, igual à A1.

Tools da Bárbara: `guardar_dados_cliente`, `escalar_para_humano`,
`encerrar_lead`. Sem `pesquisar_imoveis`/`ficha_imovel`/`agendar_visita`
(são do lado comprador) e sem `consultar_*` (fronteira de segurança do
`broker`, intocada).

## Ficheiros a alterar

| Ficheiro | Mudança |
|---|---|
| `backend/app/agents/broker/assistants.py` | `A4 = "a4_angariador"`, `NOME_A4 = "Bárbara"`, `_PROMPT_A4`, entrada em `ASSISTENTES` |
| `backend/app/agents/broker/router.py` | Separar `_ADIADO_RE` em `_A3_RE` (recrutamento, → A2) e `_A4_RE` (angariação, → A4); `route()` ganha o ramo A4 |
| `backend/app/agents/broker/guards.py` | `agente_de_lead`: `tipo == "angariacao"` → `a4_angariador` |
| `backend/app/agents/broker/tools.py` | `_NOME_AGENTE[A4] = "Bárbara"` |
| `supabase/migrations/00XX_assistente_a4_angariador.sql` | Seed `agente_config` (persona + instruções), padrão da `0014` |
| `frontend/src/components/Sidebar.jsx` | Entrada `/agentes/a4_angariador` |
| `frontend/src/i18n/pt.js` | Label de navegação |
| `frontend/src/pages/AgenteConfig.jsx` | Entrada em `META` |
| `frontend/src/pages/Chat.jsx` | Opção no selector para testar no painel |
| `backend/tests/test_router.py` | Dividir `test_a3_a4_adiados_vao_para_a2`; A4 passa a estar em `conhecidos` |

## Por confirmar com o utilizador antes de escrever o prompt final

1. **Persona/tom da Bárbara** — mesmo registo cordial de Matilde/Maria, ou
   diferente?
2. **Dados concretos para "diferenciação"** (§6.2 passo 6: tempo médio de
   venda, preço médio obtido vs. mercado) — a spec pede-os, mas não há fonte
   ainda. Ficam de fora do prompt até haver números reais, ou entram como
   texto genérico em `instrucoes`?
3. **Comissão** — informar valor concreto no prompt, ou remeter sempre para
   o consultor (mais seguro, evita a Bárbara prometer condições)?
4. Confirmar que o objectivo desta fase é **texto/routing apenas**, testado
   no chat do painel — sem tocar no WhatsApp real até validado, mesmo padrão
   seguido com o nudge da Matilde (testado com 1 número antes do cron geral).

## Verificação

- `pytest backend/tests/` — router actualizado, 244 testes actuais não
  quebram.
- Testar no `Chat.jsx` (`/api/broker/chat`, `agente=a4_angariador`) antes de
  qualquer exposição no WhatsApp.
