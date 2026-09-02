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

## Achado em produção e corrigido (2026-09-02): lead sem contacto

Uma conversa real pelo chat do site criou uma lead sem forma nenhuma de
contactar a pessoa. Causa: `find_or_create_cliente` (`guards.py`) tratava
`nome` sozinho como identificador suficiente para criar um cliente — e daí
para a frente, `_criar_lead_se_preciso` (`tools.py`) nasce mal. O próprio
docstring da função já dizia o contrário ("sem telefone nem email não se
cria cliente"), mas a condição de código não implementava isso. No WhatsApp
nunca se via, porque `contexto.get("telefone")` vem sempre do próprio
`participante`; no site não há nada a identificar quem escreve.

Fix em duas camadas:
1. **Código** (a que não pode falhar): `find_or_create_cliente` passa a
   exigir telefone OU email para criar ou actualizar — nome deixa de bastar.
   `_procurar_cliente` continua a usar o nome só para desempate (spec §2.7).
2. **Prompt**, só no canal `site` (`engine._montar_system_prompt`): instrução
   a pedir sempre nome e telefone antes de `guardar_dados_cliente` ou de
   tratar algo como interesse a registar. Não entrou na tool nem no prompt
   base do A1 para não fazer o WhatsApp perguntar um telefone que já tem.

**Confirmado ao vivo, ponta a ponta**: pedido de T2 em Buarcos sem dar
contacto → a Matilde pesquisou, mostrou opções, e só pediu nome+telefone ao
avançar para a visita — nada foi escrito na base antes disso (confirmado por
consulta directa a `agente_clientes`/`leads`). Dado o contacto, criou o
cliente com `origem='site'` e a tarefa da visita correctamente.

4 testes novos: `test_find_or_create_cliente.py` (nome sozinho não toca a
BD, nome+tipo_interesse sem contacto idem, telefone sozinho cria, email
sozinho cria) e `test_identidade_site.py` (instrução só entra no canal
`site`, WhatsApp e painel ficam como estavam).

## Por fazer (fora desta fase)

- O utilizador cola o `widget.js` no site (self-hosted, "vibe coding" —
  acesso directo ao HTML) e confirma o embed ao vivo.
- Histórico entre dispositivos e anexos ficaram fora de âmbito (ver plano).
- Se o site vier a ter mais tráfego do que uma máquina Fly aguenta, o
  rate limiter em memória tem de subir para Supabase/Redis.

## Ficheiros

- `backend/app/api/site_chat.py` (novo)
- `backend/app/api/broker.py` (`require_auth`, fix de segurança)
- `backend/app/api/deps.py` (`require_widget_key`)
- `backend/app/main.py` (router, CORS)
- `backend/app/agents/broker/assistants.py` (`MAX_TOKENS`, descrição de `guardar_dados_cliente`)
- `backend/app/agents/broker/guards.py` (`find_or_create_cliente`, gate de contacto)
- `backend/app/agents/broker/engine.py` (`_montar_system_prompt`, instrução do site)
- `backend/app/config.py` (`widget_chat_secret`)
- `backend/tests/test_site_chat.py`, `test_broker_chat_auth.py`,
  `test_find_or_create_cliente.py`, `test_identidade_site.py` (novos)
- `docs/site-chat/widget.js`, `docs/site-chat/README.md` (novos)
