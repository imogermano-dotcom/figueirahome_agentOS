# Resumo — A4 "Bárbara" implementada (código, ainda não deployada)

> Plano completo em `agente-barbara-angariacao-plano.md`. Decidido com o
> utilizador (10/09): comissão nunca no prompt (remete para o consultor),
> sem dados de diferenciação por falta de fonte, testar só no chat do painel
> antes do WhatsApp real.

## O que foi feito

- `backend/app/agents/broker/assistants.py` — `A4 = "a4_angariador"`,
  `NOME_A4 = "Bárbara"`, `_PROMPT_A4` (qualifica imóvel/zona, propõe visita
  de avaliação com dois horários concretos, nunca fala de comissão nem
  avalia o imóvel), entrada em `ASSISTENTES` com tools
  `guardar_dados_cliente` / `escalar_para_humano` / `encerrar_lead` — sem
  `pesquisar_imoveis`/`agendar_visita` (lado comprador) e sem `consultar_*`
  (fronteira do `broker`, intocada).
- `backend/app/agents/broker/router.py` — `_ADIADO_RE` dividido em `_A3_RE`
  (recrutamento, continua adiado → A2) e `_A4_RE` (angariação → A4).
- `backend/app/agents/broker/guards.py` — `agente_de_lead` mapeia
  `leads.tipo == "angariacao"` → `a4_angariador`, ao lado do que já existia
  para compra/arrendamento → A1.
- `backend/app/agents/broker/tools.py` — `_NOME_AGENTE[A4] = "Bárbara"`
  (aparece nos emails de notificação de `escalar_para_humano`).
- `supabase/migrations/0036_assistente_a4_angariador.sql` — seed de
  `agente_config` para `a4_angariador`. **Por correr à mão** no editor SQL,
  como as restantes.
- Painel: `Sidebar.jsx` (entrada 🔑 A4), `i18n/pt.js` (label), `AgenteConfig.jsx`
  (título/subtítulo/placeholders), `Chat.jsx` (opção no selector, para testar
  sem depender do WhatsApp).
- `backend/tests/test_router.py` — `test_a3_a4_adiados_vao_para_a2` dividido
  em `test_a3_recrutamento_adiado_vai_para_a2` e
  `test_a4_angariacao_vai_para_barbara` (inclui stickiness); `A4` entra em
  `conhecidos`. Suite: **245 a passar** (era 244).

## Por fazer antes de expor a clientes reais

1. Correr a migration `0036` à mão no Supabase.
2. Deploy do backend (`flyctl deploy` de dentro de `backend/`) + confirmar
   auto-deploy do frontend no Cloudflare Pages.
3. Testar no chat do painel (`/agentes/a4_angariador`, aba Configuração, ou
   `Chat.jsx` com o selector "A4 — Angariador") — **antes** de deixar
   mensagens reais de WhatsApp caírem na Bárbara.
4. Só depois disso o `router.py` (já deployado) passa a valer para o
   WhatsApp real — não há como separar as duas coisas uma vez feito o
   deploy, visto que o mesmo número serve todos os assistentes.

## Fora desta fase (ver plano)

- Tool própria para "visita de avaliação" (hoje é `escalar_para_humano`).
- Nudge 24h para a Bárbara (construído só para a A1).
- Número de WhatsApp dedicado por função.
- Dados de diferenciação (tempo médio de venda, preço vs. mercado) — sem
  fonte ainda.
