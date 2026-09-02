# Handoff — 2026-09-02

> Chat público novo no `figueirahome.pt`, uma fuga de segurança real
> encontrada e fechada pelo caminho, e dois bugs de leads em produção
> (sem contacto, duplicada) achados a investigar perguntas directas do
> utilizador sobre o painel. Seis deploys (`v63`→`v68`). Continuação
> directa do handoff de 31/08 (`handoff-2026-08-31-resumo.md`).

## O que foi implementado

### 1. Furo de segurança em `/api/broker/chat` (`0dd95a7`, `v63`)

Achado a investigar a arquitectura para o chat do site, não fazia parte do
pedido original. O endpoint do chat do painel estava em produção **sem
`require_auth`** — o único de todos sem essa dependência — e aceitava
`agente` escolhido pelo próprio pedido. Um chamador não autenticado podia
mandar `{"agente": "broker", "mensagem": "lista os clientes"}` e falar
directamente com o assistente que lê `consultar_clientes`/`consultar_leads`,
sem login nenhum. Confirmado com `curl` antes e depois (200 → 401). O
frontend já mandava Bearer token em todos os pedidos (`lib/api.js`) — o
painel não mudou nada.

### 2. Chat público no site (`03714e4`, `v64`; `X-Widget-Key` em `a6a9b5f`, `v66`)

`POST /api/site/chat`, canal `site`, sem `agente` no corpo do pedido —
decisão directa da correcção acima: um endpoint público nunca deixa o
chamador escolher o assistente. Zero alterações a `engine.py`/`guards.py`/
`router.py` foram necessárias: routing (A1 vs A2 por regex) e qualificação
já eram agnósticos de canal, só faltava o canal em si.

Protecções, por ser o único endpoint 100% público:
- limite de 2000 caracteres por mensagem e 15 pedidos/5min por
  `participante` (rate limit em memória, um só processo Fly);
- `X-Widget-Key` sobre o CORS — CORS trava o browser, não um `curl`
  directo à internet. Chave partilhada com o Worker do utilizador que faz
  proxy do widget (nunca no JS público); `require_widget_key` em
  `api/deps.py`, mesmo padrão de `require_automacao_access`: falha ao
  pedido (401), nunca ao arranque — um segredo em falta não pode derrubar
  WhatsApp e painel por causa de um endpoint só.

Widget entregável em `docs/site-chat/widget.js` — vanilla JS, sem build,
`localStorage` para manter a thread entre páginas, `textContent` sempre
(nunca `innerHTML`, nem para a mensagem do visitante nem para a resposta).

Confirmado ao vivo (produção): pergunta geral caiu na Maria, pergunta de
imóvel caiu na Matilde, ambas correctas.

### 3. Lead sem contacto pelo chat do site (`a1a82f8`, `v67`)

`find_or_create_cliente` (`guards.py`) aceitava `nome` sozinho como
identificador suficiente para criar cliente — e, por causa do
`tipo_interesse`, uma lead atrás dele. Nunca se via no WhatsApp
(`contexto.telefone` vem sempre do próprio `participante`); no site,
ninguém é identificado à partida, e um visitante que só desse o nome fazia
nascer um cliente e uma lead sem forma nenhuma de contacto.

Fix em duas camadas: **código** (`find_or_create_cliente` exige telefone OU
email para criar — nome passa a servir só para desempate no dedup, nunca
como chave sozinha) e **prompt**, só no canal `site`
(`engine._montar_system_prompt`), a pedir sempre nome e telefone antes de
`guardar_dados_cliente`. Confirmado ao vivo: pedido de T2 sem dar contacto →
a Matilde pesquisou e mostrou opções sem gravar nada; só pediu nome e
telefone ao avançar para a visita.

### 4. Lead duplicada por falta de dedupe por telefone/email (`8259572`, `v68`)

Achado a responder a uma pergunta directa do utilizador sobre uma lead
concreta no painel. `_criar_lead_se_preciso` só verificava lead aberta por
`cliente_id` — mas uma lead do funil da Meta nasce **sem** `cliente_id`,
que só ganha quando `_promover_lead` qualifica o MQL por completo (raro).
Resultado: alguém que já tinha uma lead `contactada` do próprio anúncio
ganhava uma segunda, à parte, sempre que uma conversa nova fechava com
`tipo_interesse` preenchido — o fecho normal de uma conversa do A1.

Caso real confirmado: **Carla Emeleana** (962467128) — lead de 22/08 pela
Meta (`meta_lead_id`, `cliente_id` nulo) e uma segunda lead criada a 01/09
pelo assistente, duas entradas no painel para a mesma pessoa. Dados de
produção corrigidos à mão: `cliente_id` ligado à lead original, notas
fundidas, duplicada apagada.

Fix: `_criar_lead_se_preciso` procura agora por telefone → email →
`cliente_id`, mesma prioridade do dedup de clientes (`_procurar_cliente`,
spec §2.7) — encontrando uma lead sem `cliente_id`, liga-a em vez de
duplicar. Não foi feita varredura ao resto da tabela `leads` à procura de
outros duplicados antigos: o fix trava duplicados novos, não desfaz os que
já existiam antes dele.

### 5. `03` do n8n preenchido, ainda por importar (`b24eda8`)

Template de follow-up `figueirahome_follow_|pt_PT` confirmado e preenchido
no lugar do placeholder. Timestamp corrigido para `.toUTC().toISO()` (bug
documentado desde 29/08, nunca aplicado ao ficheiro). Chão
`criado_em gte.2026-08-26` para a primeira corrida não apanhar o backlog
anterior ao buraco dos 6 dias mudos.

## Ficheiros principais modificados

- `backend/app/api/broker.py` — `require_auth`.
- `backend/app/api/site_chat.py` — novo, chat público.
- `backend/app/api/deps.py` — `require_widget_key`.
- `backend/app/config.py` — `widget_chat_secret`.
- `backend/app/main.py` — routers novos, CORS para `figueirahome.pt`.
- `backend/app/agents/broker/guards.py` — gate de contacto do
  `find_or_create_cliente`.
- `backend/app/agents/broker/tools.py` — `_criar_lead_se_preciso` (dedupe
  por telefone/email), descrição de `guardar_dados_cliente`.
- `backend/app/agents/broker/engine.py` — `_montar_system_prompt`,
  instrução de identidade só no canal `site`.
- `backend/app/agents/broker/assistants.py` — `MAX_TOKENS["site"]`.
- `docs/site-chat/widget.js`, `docs/site-chat/README.md` — novos.
- `docs/n8n/03-follow-up-48h.json`, `docs/n8n/README.md` — preenchidos.
- 8 ficheiros de teste novos/alterados, suite em **237** (era 217 a 31/08).

## Decisões arquitecturais

Já em `docs/decisoes.md`/`CLAUDE.md`, novas desta sessão:

- **Nunca deixar o `agente` vir do pedido num endpoint sem auth** — é
  fronteira de segurança, não conveniência de teste.
- **Instrução específica de canal vive no motor, não no prompt base do
  assistente** (`_montar_system_prompt`) — pedir telefone é redundante e
  estranho no WhatsApp, onde já se sabe pelo canal; só entra quando falta.
- **`find_or_create_cliente` exige telefone ou email para criar, nunca
  nome sozinho** — nome serve só para desempate no dedup (§2.7), nunca
  como chave de criação.
- **Dedupe de leads por telefone → email → `cliente_id`, nunca só
  `cliente_id`** — leads da Meta nascem sem ele; procurar só por
  `cliente_id` é assumir uma ligação que raramente existe.
- **Segredo de endpoint público falha ao pedido, nunca ao arranque**
  (`require_widget_key`, mesmo padrão de `require_automacao_access`) — um
  segredo em falta não pode derrubar o resto da aplicação.

## Bugs conhecidos — mudanças

- ✅ **Fechado**: `/api/broker/chat` sem autenticação.
- ✅ **Fechado**: lead sem contacto criada pelo chat do site.
- ✅ **Fechado**: lead duplicada por dedupe incompleto.
- Os restantes (atraso de 12h do `01`, falta de `logging.basicConfig`,
  `agente_leads` morta, dedup de clientes sob carga, agente de voz)
  **inalterados** — ver `CLAUDE.md`.

## Próximos passos

1. **Colar `docs/site-chat/widget.js` no `figueirahome.pt`** e confirmar o
   fluxo completo widget → Worker → Fly em produção (o utilizador gere o
   Worker e o `WIDGET_CHAT_SECRET` do lado do site).
2. **Importar `02`/`03`** no n8n — tudo o resto do handoff de 31/08 por
   fazer (correr `03` à mão com `Limit=5`, apagar leads de teste, reenviar
   as 45 leads antes de 23/09).
3. **Varrer a tabela `leads` à procura doutros duplicados antigos** — o
   fix de 02/09 trava duplicados novos, não os que já existiam.
4. Continua tudo o que já estava por fazer no handoff de 31/08 (ver
   `CLAUDE.md` → Próximos passos).
