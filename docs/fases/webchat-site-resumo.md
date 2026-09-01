# Resumo — Chat público no figueirahome.pt

> Plano em `webchat-site-plano.md`. Implementado e testado ao vivo no mesmo
> dia (2026-09-01).

## O que foi feito

**Furo de segurança encontrado e corrigido antes desta fase** (não fazia
parte do pedido original, achado a investigar a arquitectura para o chat
novo): `/api/broker/chat` estava em produção sem `require_auth` e aceitava
`agente` escolhido pelo próprio pedido — um chamador não autenticado podia
mandar `agente="broker"` e falar com o assistente que lê
`consultar_clientes`/`consultar_leads`. Corrigido, testado, deployado antes
de continuar (`0dd95a7`).

**Endpoint público** `POST /api/site/chat` (`api/site_chat.py`) — chama
`engine.responder(canal="site", ...)` sem `agente`, sem `require_auth`
(é para visitante anónimo). Sem campo `agente` no schema: o router decide
sempre, replicando a decisão de segurança acima em vez de a contornar.

**Protecção de abuso** — único endpoint 100% público: limite de 2000
caracteres por mensagem e 15 pedidos/5min por `participante`, em memória
(`# ponytail`, ver plano — aceitável com 1 máquina Fly).

**CORS** — `figueirahome.pt`/`www.figueirahome.pt` acrescentados em
`main.py`, sem tocar no regex do painel.

**`MAX_TOKENS["site"] = 768`** em `assistants.py`.

**Widget** `docs/site-chat/widget.js` + `README.md` — vanilla JS, sem build,
bolha flutuante, `localStorage` para manter a thread entre páginas. Todo o
texto vai por `textContent`, nunca `innerHTML` — nem a mensagem do
visitante nem a resposta do agente são código de confiança.

**Confirmado ao vivo** (uvicorn local, API real): pergunta geral
("que horário tem a agência?") caiu na Maria (A2) com a resposta certa do
`agente_config`; pergunta de imóvel ("procuro T2 em Coimbra até 200 mil")
caiu na Matilde (A1), que respondeu correctamente que a agência só cobre a
Figueira da Foz e ofereceu pesquisar alternativas — zero alterações a
`engine.py`, `guards.py` ou `router.py` foram necessárias.

## Testes

6 novos (`test_site_chat.py`): resposta usa canal `site` sem `agente`,
`agente` no corpo do pedido é ignorado, mensagem vazia/demasiado longa
rejeitada (422), rate limit por participante (429) e não-global. Mais 1
(`test_broker_chat_auth.py`) para o fix de segurança. Suite: **226**
(era 219 no handoff anterior).

## Por fazer (fora desta fase)

- O utilizador cola o `widget.js` no site (self-hosted, "vibe coding" —
  acesso directo ao HTML) e confirma o embed ao vivo.
- Histórico entre dispositivos e anexos ficaram fora de âmbito (ver plano).
- Se o site vier a ter mais tráfego do que uma máquina Fly aguenta, o
  rate limiter em memória tem de subir para Supabase/Redis.

## Ficheiros

- `backend/app/api/site_chat.py` (novo)
- `backend/app/api/broker.py` (`require_auth`, fix de segurança)
- `backend/app/main.py` (router, CORS)
- `backend/app/agents/broker/assistants.py` (`MAX_TOKENS`)
- `backend/tests/test_site_chat.py`, `test_broker_chat_auth.py` (novos)
- `docs/site-chat/widget.js`, `docs/site-chat/README.md` (novos)
