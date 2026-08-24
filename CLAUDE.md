# CLAUDE.md — Figueirahome Agent Call

> Contexto principal do projecto. Lido automaticamente em cada sessão.

## O que é

Plataforma de IA para agência imobiliária em Portugal:
1. **Assistentes de atendimento** — **A1 Vendedor "Matilde"** (compradores e arrendatários) e
   **A2 Geral "Maria"** (recepção e encaminhamento), em WhatsApp e no painel.
2. **Agente de Voz** — atendimento telefónico (Telnyx). Bloqueado por credenciais.
3. **Assistente Broker** — chat interno do corretor, com acesso de leitura à BD.
4. **Painel de gestão** — React: clientes, imóveis, leads, métricas dos assistentes.
5. **Landing pages por imóvel** — páginas públicas geradas por IA, para anúncios.

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | React + Tailwind v4 (Vite) → Cloudflare Pages |
| Backend | FastAPI (Python, async) → Fly.io. Landing pages em Jinja2 + CSS à mão |
| Base de dados | Supabase (PostgreSQL + Auth) — 2 projectos |
| Telefonia / STT / TTS | Telnyx (Call Control + Streaming) · OpenAI Whisper (PT) · Telnyx `speak()` (`Polly.Ines-Neural`) |
| IA | Claude API — Sonnet 4.6 (httpx directo, não SDK) |

## Estrutura

```
backend/app/
├── main.py · config.py (pydantic-settings: SUPABASE_*, EGOREALESTATE_*, AUTOMACAO_SECRET)
├── api/             ← clientes, imoveis, imoveis_sync, oportunidades_sync, leads, tarefas,
│                      config, dashboard, broker, agentes, landing ⑂ (/lp/* + painel),
│                      leads_meta (semeadura das leads da Meta — n8n)
├── landing/ ⑂       ← gerador.py (allowlist pública + hash + API) · templates/
├── agents/
│   ├── voice/       ← webhook Telnyx, audio_ws, save_call, claude_agent (só voz)
│   └── broker/      ← engine (motor único), assistants (registry), router, guards
│                      (dedup + 80% + qualificação), custos, tools, conversation,
│                      channels/whatsapp/
├── integrations/    ← egorealestate.py (cliente API), imoveis_sync.py (upsert + extras)
├── db/supabase_client.py  ← get_supabase() [dados] + get_supabase_auth() [só login]
└── models/          ← Pydantic (imovel, cliente, lead, tarefa, ...)

frontend/src/  App.jsx · lib/ · components/ (Layout, Sidebar, AgenteMetricas,
  AgenteConversas, Barras, LandingPagesTab ⑂, ui.jsx ⑂) · pages/ (Dashboard,
  Clientes, Imoveis, Leads, Chat, AgenteConfig, Config)
scraper/       app Fly.io separada, Playwright + upsert do eGO (oportunidades,
  notas, tarefas, visitas, contactos) — ver docs/decisoes.md
cloudflare/ ⑂  worker-landing.js (proxy site.pt/imovel/* → /lp/*)
```

**⑂ = só existe no ramo `feat/landing-pages`, não em `master`.**

## Estado actual — Handoff 2026-08-23

1. **Leads da Meta** — a correr ao vivo. Os três desfechos da spec §2.2 são a
   fase de hoje: **`0030` por correr, tudo por deployar** (ver abaixo).
2. **Landing pages** — construída desde 08-08, isolada no ramo
   **`feat/landing-pages`**, em standby à espera da decisão de alojamento do
   cliente. Não deployar, não fazer merge.

### Produção

| Componente | Estado |
|---|---|
| Backend `figueirahome-agentos.fly.dev` | ✅ deployado 2026-08-24 em `809dfb3` (`v49`, 512mb) — leads da Meta, qualificação, os três desfechos (`encerrar_lead`, `sem_resposta`, email da visita), visitas virtuais (`0028`), apresentação da Matilde, notificações Graph (inertes sem credenciais). **Sem** landing pages |
| Frontend `figueirahome-agentos.pages.dev` | ✅ Cloudflare Pages, auto-deploy do push |
| Scraper `figueirahome-scraper.fly.dev` | ✅ deployado 2026-08-15 em `7b1843f` — visitas em tabela própria, espera pela barra lateral do eGO, e um contacto impossível deixa de matar o lote |
| Assistentes A1/A2 | ✅ WhatsApp + painel, com pesquisa de imóveis reais |
| Crons eGO (GitHub Actions) | ✅ `sync-imoveis.yml` **06:00 UTC** (~43 s) e `sync-oportunidades.yml` **03:00 UTC**. Chamam o **Fly.io**, não o repo — sem deploy correm código antigo. Afastados de propósito: ambos entram no backoffice com a mesma conta, e correram juntos a 08-18 com OOM. O tecto das oportunidades é o `timeout=240` do backend, não o `--max-time` do curl |
| `master` | ✅ pushed e deployado. Landing pages **fora** de `master`, no ramo `feat/landing-pages` |

### Fase de hoje — os três desfechos da spec §2.2 (deployada)

Faltavam dois e meio dos três. **Engano** (não existia): tool `encerrar_lead`,
escrita em `guards.encerrar_lead_do_telefone`, "Sem mais ações" à letra.
**Sem resposta 48h** (não existia): `0030` (`follow_up_em`, o travão) +
`docs/n8n/03-follow-up-48h.json`, diário às 10h Lisboa. **Interesse real**
(parcial): a visita passou a avisar por email, e a Matilde propõe horários em vez
de os perguntar. `0030` aplicada; **falta o template de follow-up aprovado na
Meta** e correr o `03` à mão. **27 leads elegíveis** a 24/08.

### Visitas do eGO — `0023` aplicada, scraper deployado 2026-08-15

Uma oportunidade só guardava **1 visita** (o eGO dá uma linha por visita e o
`setdefault` em `group()` ficava com a primeira; medido: 1739 com visita, máximo
de 1). Tabela `visitas` própria (`visita_ref_ego`), aditiva — `oportunidades`
fica intacta por causa do portal do Miguel. O histórico perdido só volta
reprocessando um export com período largo; adiado.

### Landing pages — standby no ramo `feat/landing-pages`

Detalhe em `docs/fases/landing-pages-resumo.md` (no ramo). `0020` por correr,
zero gerações reais. Espera a decisão de alojamento: **A** (HTML do backend +
Worker Cloudflare, gate real) vs **B** (estático, gate cosmético e `anon`
exposta). Recomendação registada: **A**.

⚠️ **`flyctl deploy` envia a árvore de trabalho, não o HEAD** e o
`backend/.dockerignore` não exclui as landing pages — **merge antes da `0020`
põe `/lp/*` no ar a dar 500**. Deployar de `git worktree add <tmp> master`.
`POST /lp/{slug}/lead` continua **sem rate-limit** (só honeypot).

### Invariantes que não são óbvias a ler o código

- **Features do imóvel ≠ zona envolvente** nas `FeatureTags` do eGO: `SWIMMING_POOLS`/`PROPERTY_NEAR_GARDENS` são "há na zona"; as do imóvel são `PROPERTY_HAS_POOL`/`PROPERTY_HAS_GARDEN`. A tag errada põe o A1 a afirmar ao comprador o que o imóvel não tem.
- **Upsert por lotes do PostgREST**: uma chave presente num só registo vira coluna e escreve NULL em todos os outros. Omitir a chave não protege — custou 40 coordenadas. Esparsos saem por `_map_extras`, UPDATE linha a linha.
- **`latitude`/`longitude` só com `HasGPSLocation=true`** (13/55): sem o flag o eGO devolve o centróide da zona — 42 imóveis em 10 pontos, 19 no mesmo. A guarda vive no `_gps`, mas a chave tem de ser escrita pelo **`_map_property`**: no `_map_extras`, que filtra nulos, impedia escrever e nunca apagava — 40 linhas ficaram com o centróide até 2026-08-18.
- **O eGO demora ~10 min** a expor um imóvel novo na Web API; sincronizar logo a seguir a publicar não o apanha. **Prompt caching a 67%** — "Servido de cache" a zero havendo turnos multiplica o custo por 10.
- **Três allowlists são fronteiras de segurança**, todas com teste: `_TOOLS_INPUT_SEGURO`, `gerador.CAMPOS_PUBLICOS`, `_FEATURE_BOOLS`.
- **MQL = orçamento + zona + tipo de interesse** (`guards.lead_qualificada`); o timing só vem do gate das landing pages. **Imóveis contam-se por `publicado` (53)**, não `disponibilidade`.
- **Visitas de um imóvel contam-se por `visitas.visita_imovel_ref`**, nunca por `oportunidades.imovel_ref` — a segunda é o imóvel da *oportunidade* e perde quem visitou vindo de outra (FH2571: 7 contra 4). O painel não mostra visitas do eGO; `visitas_pendentes` no Dashboard vem de `agente_tarefas`.
- **WhatsApp não lê Markdown** — `channels/whatsapp/formatacao.py`, ponto único de saída. **Sem gráficos de evolução nem de receita** — os dados mentiriam (`dashboard-plano.md`).

### Dados

Tudo no projecto Supabase `zphasvfopnbzwnaidsnw` (settings `supabase_imoveis_*`);
o original é **só Auth**. `get_supabase()` = dados, `get_supabase_auth()` = login.
**Migrations corridas à mão pelo utilizador** no editor SQL — explicar antes.
Três tabelas de leads, de propósito: **`leads`** (`0021`, genérica — é para aqui
que as outras convergiram, `0029` deu-lhe `origem`), `agente_leads` (morta desde
2026-08-18 — sem escritores nem leitores, por apagar) e `leads_angariacao`
(79, fluxo humano Make + consultora). **`oportunidades`/`contactos` são de fora
do repo** — não gerir daqui; o portal do Miguel também as lê.

### Ambiente local

- Python `...\Python312\python.exe` · fly `C:\Users\joaoa\.fly\bin\flyctl.exe deploy --app <nome>`
- `.env`: Supabase ✅, Anthropic ✅, OpenAI ✅, eGO API+CRM ✅, SCRAPER_* ✅, **AUTOMACAO_SECRET ❌**, Telnyx ❌, Meta ❌
- Testes: `pytest backend/tests/` de `backend/` — **130**. Scraper: `python upsert.py` e `python mapping_todas_colunas.py` de `scraper/`

### Bloqueadores activos

| Item | Estado |
|---|---|
| `AUTOMACAO_SECRET` | ⬜ **já não bloqueia** — o fluxo não passa por endpoint nosso (`0024`). Só é preciso se se voltar a semear |
| **Portal do Miguel** | ⚠️ ainda em vigor, lê o mesmo Supabase. **Bloqueia a `0022`**: se usar a chave `anon`, apertar o RLS de `contactos`/`imoveis`/`oportunidades` parte-o. Confirmar a chave antes de correr |
| `whatsapp_permissao` a `True` em **3 de 79** | ⚠️ é o gate do template; se o Make não o marcar à entrada, não sai template e não há A1 |
| Formulário de venda do Meta Lead Ads | ⚠️ não existe ainda; os alias em `_ALIAS_FICHA` são palpites tirados do de angariação |
| Telnyx — credenciais e número PT +351 | ❌ bloqueia a voz · ~3459 linhas `fonte='manual'` de origem desconhecida: parado a pedido do utilizador |

### Próximos passos

0. **Fechar a fase dos desfechos**: `0030` ✅ e deploy ✅. Falta o **template de follow-up aprovado na Meta** (é outro, não o do fluxo 01), importar o `03-follow-up-48h.json` e correr **à mão com `Limit=5`** antes de activar a agenda — contagem de controlo no `docs/n8n/README.md`.
1. **Validar em produção**: correr "Validar CRM" no painel (resolve os 12 imóveis em limbo) e uma lead de teste ponta a ponta. Backend e scraper já deployados.
2. **Campos reais do formulário de venda** (`_ALIAS_FICHA` em `guards.py` é palpite — sem isto o A1 entra cego e a lead nunca qualifica) e **chave do portal do Miguel** → desbloqueia a `0022` (RLS). E **decidir as 70 do CRM** (`imoveis_sync.py:442` só cria estado "Disponível" — 61 Por validar, 7 Arrendado, 2 Reservado ficam de fora, sem sinalização).
3. **Confirmar com o Make/n8n**: campos reais do formulário de venda (`_ALIAS_FICHA`) e quem marca `whatsapp_permissao`. **Decisão de alojamento das landing pages** bloqueia essa fase toda.
4. **Apagar `agente_leads`** (migration própria, depois de a reforma correr uns dias) e **actualizar `landing.py:223` no ramo `feat/landing-pages`** — é o único escritor que sobrou, e sem isso o merge ressuscita a tabela morta.
5. **Passagem automática ao eGO** (precisa da chave de integração) · **A3/A4 e sub-fluxos SC/FP** (adiados; `agente_clientes` sem coluna `agente`) · **lembretes 24h/48h** (precisam de scheduler).
6. **Dados a montante**: `responsavel` com "Internet" (892), 8432 sem `data_criacao_iso`, `valor_negocio` quase vazio. Recuperação do histórico de visitas (export com período largo).

## Decisões arquitecturais

**Texto completo e o porquê de cada uma: `docs/decisoes.md`.** Ler antes de mexer
na área respectiva — quase todas registam uma tentativa que já falhou ao vivo.

- **Um motor, N assistentes** — nunca N cópias do loop. A3/A4 = entrada no dict + linha em `agente_config`, que é **a tabela de assistentes** (acrescentar = INSERT, não deploy).
- **Subconjunto de tools por assistente é fronteira de segurança**, não organização (`consultar_*` só no `broker`).
- **Router por regex, não por LLM**; routing **sticky** em `agente_conversas.agente`, sentido único A2→A1.
- **Regras que não podem falhar vivem em `guards.py`** (dedup + 80%), nunca no prompt. **Dedup: o nome é sempre tentado**, aceite só quando nada contradiz (`_compativel`).
- **Fallback de tipologia dentro da tool** — o modelo perdia moradias T2 ao traduzir "T2"→`natureza`. **Tool forcing** na iteração 0 quando `_SEARCH_RE` bate; sem ele Claude prometia callbacks.
- **Assistentes nunca escrevem em `oportunidades`/`contactos`** — espelho do eGO, pipeline externo. A lead qualificada pára numa **tarefa** (+ email ao corretor, `notificacoes.py`): não há API de escrita do eGO, e um insert nosso em `contactos` fica órfão.
- **Leads da Meta: semear a conversa, não mexer no router** — a resposta a um template é "Sim"/"Olá", que `_A1_RE` não apanha. A thread nasce com `agente='a1_vendedor'`; alargar o regex mandaria para o A1 toda a gente que diz "olá".
- **`load_conversation` procura por variantes do número** — a Meta manda `351…`, a semeadura guarda 9 dígitos. Com `.eq()` exacto a thread nunca era encontrada e a funcionalidade parecia instalada sem fazer nada.
- **Qualificação: regra única em `guards.py`, dois gatilhos** — `find_or_create_cliente` (escrita de cliente) e `promover_se_qualificada` (fim de turno). Sem o segundo, a lead cujo formulário já traz o MQL nunca era promovida. `nova` só conta como "respondeu" no segundo.
- **Desfecho de conversa ≠ qualificação** — os três da spec §2.2 entram **ao lado** do MQL, não por cima. **`engano` fecha** (sai de `_ESTADOS_LEAD_ABERTA`, entra em `ESTADOS_FECHADOS`); **`sem_resposta` fica ABERTO** apesar do nome — quem responde tarde tem de manter a Matilde e o `imovel_ref`. Detecção do engano por **tool**, escrita em código; o travão do follow-up é a **coluna `follow_up_em`**, nunca o estado (o estado é editável no painel).
- **Visitas em tabela própria (`visitas`, `0023`)** — em colunas de `oportunidades` cabia 1 por oportunidade e o eGO dá uma linha por visita. `oportunidades` fica intacta: o portal do Miguel lê-a.
- **Segredo próprio para automações** (`X-Automacao-Secret`) — Make e n8n não têm de poder disparar syncs do eGO; segredo vazio nunca autentica.
- **Refs duplicadas do eGO desempatam por data de alteração**, não pela ordem da lista — a ordem escolhia a cópia por preencher (FH2460 4D gravava piso 0 num 4.º andar).
- **Landing pages em HTML servido pelo backend**, não rota do SPA — as OG tags têm de existir no HTML (WhatsApp). **`fonte_hash` decide se se regenera.** **`publicado` é coluna GENERATED**; `disponivel_na_api` é a excepção escrita pela app.
- **Sync eGO sempre full** (`?Since=` avariado). **Validação CRM completa só manual** (no cron sobrepunha estados que a API já confirmava) — **excepto restrita aos refs que saíram da API**, e essa corre **depois do upsert, nunca antes**: raspa o backoffice inteiro, e à frente do upsert estourou o `--max-time` do cron e matou o sync dois dias seguidos. **RAM da app principal é escassa**: Playwright nunca lá (`scraper/` tem app própria), e o `fetch_all` do backoffice obrigou a subir de 256 para **512mb** — em 256 o uvicorn morria por OOM a meio do sync.

## Bugs conhecidos

- **`agente_leads` ainda existe**, agora vazia de uso — nada lhe escreve nem lê desde 2026-08-18. Só desaparece a confusão quando for apagada (Próximos passos 4).
- **Dedup de clientes sob carga**: teste falhou e voltou a passar com o mesmo código. Se aparecerem duplicados em produção, é por aqui.
- **Landing pages nunca correram contra dados reais** — zero gerações, `0020` por aplicar, custo estimado; **`POST /lp/{slug}/lead` sem rate-limit** (só honeypot).
- **Agente de voz** (bloqueado por Telnyx, não se manifesta hoje): sem barge-in; sessões em memória, perdidas em restart; race condition (`is_speaking` vs `call.speak.ended`); janelas fixas de 2 s sem VAD.

## Convenções

- **Python:** PEP 8, type hints, async. **React:** funcionais + hooks, sem classes.
- **Nomes:** código em inglês; UI em PT-PT. **DB:** português, snake_case.
- **Segredos:** nunca hardcoded. Só em `.env` / Fly.io secrets.
- ⚠️ **O repositório GitHub é PÚBLICO** (`imogermano-dotcom/figueirahome_agentOS`).
  Varrido a 2026-08-13: zero credenciais, zero dados de clientes — os telefones
  em código são todos `912345678`, os emails são placeholders, os `.env.example`
  só têm `YOUR_*`. O que está exposto é arquitectura e método, não segredos.
  **Material interno da agência não entra** — ver `kb-a1-vendedor.md` no
  `.gitignore` e a decisão respectiva em `docs/decisoes.md`.
- **Excepção:** os templates das landing pages não usam Tailwind — CSS à mão, zero
  pedidos externos, porque a página abre a partir de um anúncio pago.

## Regras para o Claude Code

1. Ler `docs/PRD.md` antes de feature nova; `docs/database-schema.md` antes de
   tocar na DB; `docs/api-spec.md` antes de criar/alterar endpoints;
   `docs/decisoes.md` antes de contrariar uma decisão.
2. **Fase nova → seguir `planeamento-fases.md`. Plano antes de código. Sempre.**
   Uma fase de cada vez; primeira resposta = plano, nunca código directo.
3. Manter este ficheiro actualizado após cada fase. **Limite: 200 linhas** — o
   histórico vai para `docs/fases/`, as decisões para `docs/decisoes.md`.
4. Nunca inventar credenciais.
