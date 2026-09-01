# Plano — Chat público no figueirahome.pt

> Fase nova, plano antes de código (regra do CLAUDE.md). `figueirahome.pt` é
> o site institucional da agência, feito pelo utilizador ("vibe coding"),
> fora deste repositório — acesso directo ao HTML, sem CMS. Não confundir
> com `imoveis.figueirahome.pt` (SPA de imóveis) nem com o painel interno
> (`figueirahome-agentos.pages.dev`).

## Objectivo

Widget de chat embutido no site público — apoio + pesquisa de imóveis —
respondido por um agente. Visitante anónimo, sem login.

## O que já existe e se reaproveita, sem alterar

`engine.responder(canal, participante, mensagem, agente=None)` já é
agnóstico de canal — é chamado hoje por WhatsApp e pelo chat interno do
painel. Com `agente=None`, `router.route()` decide A1 (compra/arrendamento/
pesquisa) vs A2 (geral, escala o resto) por regex, sem chamada extra ao
modelo. **A qualificação de lead não depende do canal**: `guardar_dados_cliente`
→ `find_or_create_cliente` (guards.py:442) promove pela `lead_qualificada()`
usando só nome/telefone/email que o próprio modelo recolhe na conversa — os
mesmos três campos que o A1 já pede no WhatsApp. Um visitante do site que
dê nome + telefone + orçamento + zona gera tarefa e email ao corretor
exactamente como uma lead do WhatsApp, sem tocar em `engine.py` nem em
`guards.py`.

Ou seja: a parte "agente a responder" está pronta. O que falta é o canal.

## O que é novo

### 1. Endpoint público, sem `agente` no pedido

`api/broker.py` acabou de ganhar `require_auth` (fix de segurança de
2026-08-31) porque aceitava `agente` escolhido pelo chamador — um caminho
directo ao assistente `broker` (lê `consultar_clientes`/`consultar_leads`).
**Não reabrir essa porta**: o endpoint novo é público de propósito (visitante
sem login), por isso o corpo do pedido nunca inclui `agente` — o router é
sempre quem decide, tal como no WhatsApp.

`POST /api/site/chat`
```json
{"participante": "<uuid gerado no browser>", "mensagem": "texto"}
```
→ `responder(canal="site", participante=participante, mensagem=mensagem)`
(sem `agente`). Novo router `api/site_chat.py`, sem `Depends(require_auth)`,
sem campo `agente` no `BaseModel` — a ausência do campo é a garantia, não uma
validação a mais que se possa esquecer de chamar.

`canal="site"` e não `"web"`: o `"web"` já é usado pelo chat de teste do
painel (`participante="painel_<agente>"`) — misturar as duas séries de
threads na mesma tabela com o mesmo canal dificultava distinguir teste de
visitante real.

### 2. Protecção de abuso (é o único endpoint 100% público e sem segredo)

Sem isto, qualquer pessoa manda tráfego ilimitado para a API da Anthropic à
nossa conta:
- limite de tamanho de mensagem (ex.: 2000 caracteres);
- limite de pedidos por `participante` numa janela curta (ex.: 15/5min).

`# ponytail: limitador em memória, por processo — aceitável com 1 máquina
Fly (é o estado actual). Sobe para Supabase/Redis se algum dia houver >1
máquina, senão cada máquina conta separado e o limite triplica sem avisar.`

### 3. CORS

`main.py` só permite `settings.frontend_url` e `*.pages.dev` em produção.
Acrescentar `https://figueirahome.pt` (e `https://www.figueirahome.pt`) à
lista de origens — sem isto o browser bloqueia o `fetch` do widget antes de
chegar ao backend.

### 4. O widget

Ficheiro único, sem build (o site não tem pipeline): HTML/CSS/JS
autocontidos, bolha flutuante + painel de conversa. Gera um `participante`
(UUID) na primeira visita e guarda em `localStorage` — mesma thread ao
navegar entre páginas do site, sem histórico entre dispositivos.

Entregável: `docs/site-chat/widget.js` (+ instruções). O utilizador cola o
ficheiro no seu site e adiciona uma linha:
```html
<script src="/caminho/para/widget.js" defer></script>
```
Não hospedado por nós — o site é dele, edição directa.

### 5. `MAX_TOKENS`

`assistants.py` tem `{"whatsapp": 512, "web": 1024}`. Acrescentar
`"site": 768` — visitante de site em ecrã pequeno tolera menos do que o
painel do corretor mas mais do que WhatsApp.

## Fora de âmbito nesta fase

- Histórico entre sessões/dispositivos (precisaria de login).
- Notificação em tempo real ao corretor de que "alguém está no chat agora"
  — a lead qualificada já gera tarefa + email, isso basta para o MVP.
- Anexos/imagens no chat.

## Ficheiros a tocar

| Ficheiro | Mudança |
|---|---|
| `backend/app/api/site_chat.py` | novo — endpoint público |
| `backend/app/main.py` | incluir router, CORS para figueirahome.pt |
| `backend/app/agents/broker/assistants.py` | `MAX_TOKENS["site"]` |
| `backend/tests/test_site_chat.py` | novo — sem `agente` no schema, limite de tamanho, rate limit |
| `docs/site-chat/widget.js` | novo — entregável |

## Como se testa

`pytest` cobre o endpoint (schema, rate limit, ausência de `agente`) sem
tocar na API da Anthropic (mesmo padrão de mocks já usado nos outros
testes). O widget testa-se ao vivo: correr `uvicorn` local, abrir o
`widget.js` num HTML de teste, confirmar que uma pergunta de compra cai no
A1 e uma pergunta institucional cai no A2.
