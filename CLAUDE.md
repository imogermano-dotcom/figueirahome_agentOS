# CLAUDE.md — Figueirahome Agent Call

> Contexto principal do projecto. Lido automaticamente em cada sessão.

## O que é

Plataforma de IA para agência imobiliária em Portugal:
1. **Assistentes** — **A1 "Matilde"** (compra/arrendamento), **A2 "Maria"** (recepção e encaminhamento), **A3 "Inês"** (recrutamento) e **A4 "Bárbara"** (angariação), em WhatsApp, no painel e no site público (`figueirahome.pt`).
2. **Agente de Voz** — atendimento telefónico (Telnyx). Bloqueado por credenciais.
3. **Assistente Broker** — chat interno do corretor, leitura da BD. **Painel** React: clientes, imóveis, leads, métricas.

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | React + Tailwind v4 (Vite) → Cloudflare Pages |
| Backend | FastAPI (Python, async) → Fly.io. Landing pages em Jinja2 + CSS à mão |
| Base de dados | Supabase (PostgreSQL + Auth) — 1 projecto (fundido em 13/09) |
| Telefonia / STT / TTS | Telnyx (Call Control + Streaming) · OpenAI Whisper (PT) · Telnyx `speak()` (`Polly.Ines-Neural`) |
| IA | Claude API — Sonnet 4.6 (httpx directo, não SDK) |

## Estrutura

```
backend/app/
├── main.py · config.py (pydantic-settings: SUPABASE_*, EGOREALESTATE_*, AUTOMACAO_SECRET)
├── api/             ← clientes, imoveis, imoveis_sync, oportunidades_sync (completo + tarefas),
│                      leads, tarefas, config, dashboard, broker, agentes, landing ⑂,
│                      leads_meta (semeadura das leads da Meta — n8n)
├── landing/ ⑂       ← gerador.py (allowlist pública + hash + API) · templates/
├── agents/voice/    ← webhook Telnyx, audio_ws, save_call, claude_agent (só voz)
├── agents/broker/   ← engine (motor único), assistants, router, guards (dedup +
│                      80% + qualificação), custos, tools, conversation, nudge
│                      (lembrete A1/A3/A4), channels/whatsapp/ (webhook, meta_api, formatacao)
├── integrations/    ← egorealestate.py (cliente API), imoveis_sync.py (upsert + extras)
├── db/supabase_client.py  ← get_supabase(), cliente único (projecto de dados + Auth fundidos)
└── models/          ← Pydantic (imovel, cliente, lead, tarefa, ...)

frontend/src/  App.jsx · lib/ · components/ (Layout, Sidebar, AgenteMetricas, · AgenteConversas, Barras, LandingPagesTab ⑂, ui.jsx ⑂) · pages/ (Dashboard,  · Clientes, Imoveis, Leads, Chat, AgenteConfig, Config)
scraper/  app Fly.io separada, Playwright: oportunidades_completo, tarefas (sync), mapping_todas_colunas, upsert · cloudflare/ ⑂
crons/    Cron Manager no Fly (app figueirahome-crons): schedules.json
```

**⑂ = só existe no ramo `feat/landing-pages`, não em `master`.**

## Estado actual — Handoff 2026-10-03

Continuação do handoff de 29/09. Detalhe completo: `docs/fases/handoff-2026-10-03-resumo.md`. Sessão de 29/09 a 03/10: Inês corrigida, tarefas do eGO sincronizadas por cron, e `contacto_id` para relacionar as tabelas pelo ID do contacto (**backfill do histórico por correr**).

- **`contacto_id` em `oportunidades`/`tarefas`/`notas`/`visitas` (01/10)** — migration `0046` (aplicada à mão) + RPCs `set_contacto_oportunidades`/`propagar_contacto_id`. O scraper grava `contactos` primeiro e liga por `ego_link`. A 03/10: **46/26 058 oportunidades ligadas** (`contacto_match='ego_link'`), cresce com as edições. **Falta o backfill do histórico** (`docs/fases/contacto-id-backfill.sql`, ~82% por telefone/email/nome). `contacto-id-plano.md`.
- **Tarefas do eGO (30/09)** — `scraper/tarefas.py sync`: snapshot das 2192 activas em 4 fatias por data de criação, upsert em `tarefas`, fecha (`concluida`) as nossas `pendente` que saíram. Cron `sync-tarefas` 05:07 UTC (job 6): **correu sozinho 01, 02 e 03/10**. `tarefas-sync-plano.md`.
- **Inês (A3), 29/09 (v106)** — recebe o contexto da candidatura Meta (`engine._contexto_recrutamento`); resposta sem texto já não vira "Ocorreu um erro" (`erro=sem_texto`); lead de recrutamento nasce `tipo='recrutamento'` e volta à Inês (`guards.agente_de_lead`); prompt sem pedir telefone no WhatsApp nem prometer prazos.
- **Atribuição Meta ads** (`ad_id`/`ad_name`/`adset_*`, `0045`) **testada com lead real (29/09)**, sem duplicar (`contactos-atribuicao-ads-resumo.md`). `telefone`/`telemovel` unificados em `contactos`; `oportunidades.cliente_telefone/email` espelhados do contacto.

### Produção

| Componente | Estado |
|---|---|
| `sync-tarefas` (cron 05:07 UTC) | ✅ a correr sozinho desde 01/10 |
| `contacto_id` (`0046`, scraper) | ✅ migration e scraper deployados; ⚠️ backfill do histórico por correr |
| Atribuição Meta ads, Inês (A3, v106) | ✅ 29/09 |
| `Meta leads to supabase`, templates `01`/Angariação/Recrutamento (n8n) | ✅ 15/09–25/09 — testados com lead real |
| A1 `pedir_visita`, Nudge (A1/A3/A4), estado `pausa` | ✅ 18/09–28/09 |
| Backend/Scraper/Frontend/Crons | ✅ (03/10). `master`: 2 commits locais por enviar (`contacto_id`) |

### Fases anteriores — deployadas, detalhe em `docs/fases/`

- **28/09** `pausa`, A3 sem comissão, log `erro_whatsapp` (`lead-pausa-resumo.md`) · **25/09** WhatsApp multi-número, routing/RPCs Meta, nudge, lock de conversas (`meta-leads-routing-rpcs-resumo.md`, `nudge-todos-agentes-resumo.md`, `lock-conversas-concorrentes-resumo.md`)
- **21–23/09** `contactos` espelhado, Recrutamento A3, Angariação A4, Cron Manager (`recrutamento-followup-resumo.md`, `angariacao-followup-resumo.md`, `cron-manager-fly-resumo.md`)
- **13–20/09** A4 "Bárbara", leads Meta → n8n, `contactos` unificado, A1 sem agendamento (`handoff-2026-09-13-resumo.md`, `leads-meta-n8n-resumo.md`, `handoff-2026-09-20-resumo.md`)
- **Landing pages**: no ar, fora deste repo; construtor (`feat/landing-pages`) parado por decisão do cliente.

### Invariantes que não são óbvias a ler o código

- ⚠️ **`flyctl deploy` envia a árvore de trabalho, não o HEAD**, e o `.dockerignore` não exclui as landing pages: **fazer merge do `feat/landing-pages` antes de correr a `0020` põe `/lp/*` a dar 500**.
- **Features do imóvel ≠ zona envolvente** nas `FeatureTags` do eGO: `SWIMMING_POOLS`/`PROPERTY_NEAR_GARDENS` são "há na zona"; as do imóvel são `PROPERTY_HAS_POOL`/`PROPERTY_HAS_GARDEN`. A tag errada põe o A1 a afirmar ao comprador o que o imóvel não tem.
- **Upsert por lotes do PostgREST**: uma chave presente num só registo vira coluna e escreve NULL em todos os outros — custou 40 coordenadas e é por isso que `contacto_id` só se escreve por RPC. Esparsos saem por `_map_extras`, UPDATE linha a linha. **`latitude`/`longitude` só com `HasGPSLocation=true`** (sem o flag o eGO devolve o centróide da zona); a chave tem de ser escrita pelo **`_map_property`**, não pelo `_map_extras` (que filtra nulos e nunca apagava).
- **O eGO demora ~10 min** a expor um imóvel novo na Web API. **Prompt caching a 67%** — "Servido de cache" a zero havendo turnos multiplica o custo por 10.
- **O `ID` da Web API do eGO (`imoveis.ego_id`) não é o do backoffice** (`/egocore/realestate/{id}`): passar o nosso lá devolve sempre "não pode consultar", indistinguível de bloqueio. Obtém-se por `find_by_ref`, nunca por `fetch_detail(ego_id)`. **Um imóvel pode ter vários registos internos na mesma referência** (`FH2483_A`: 3), só um exposto na Web API.
- **Três allowlists são fronteiras de segurança**, todas com teste: `_TOOLS_INPUT_SEGURO`, `gerador.CAMPOS_PUBLICOS`, `_FEATURE_BOOLS`. **A quarta não se vê em Python**: o consentimento de WhatsApp vem de um *trigger* na base (`tgr_normaliza_aceita_whatsapp`, `0031`).
- **O repo não é a fonte de verdade única do esquema** — entradas em `supabase_migrations` vieram da interface do Supabase. **`db push` proibido** (a `0001` aborta); CLI só de leitura. `supabase migration list` antes de confiar no `database-schema.md`.
- **MQL = orçamento + zona + tipo de interesse** (`guards.lead_qualificada`). **Imóveis contam-se por `publicado`**, não `disponibilidade`. **A lead responde na 1.ª hora ou nunca** (16 de 17 reais) e 13 das 17 conversas foram ao fim-de-semana — a premissa das 48h do follow-up não está confirmada.
- **Visitas de um imóvel contam-se por `visitas.visita_imovel_ref`**, nunca por `oportunidades.imovel_ref` (FH2571: 7 contra 4). `visitas_pendentes` no Dashboard vem de `agente_tarefas`.
- **`200 accepted` da Graph API NÃO é entrega.** O n8n marca `template_enviado_em` com o 200 — durante 6 dias marcou 45 leads como contactadas que nunca receberam nada. Quando a Matilde emudecer, **ver a faturação da WABA antes de culpar o conteúdo**.
- **O n8n não valida nada do que lá se escreve**: um nome de coluna trocado no `filterString` devolve linhas a mais em silêncio, e uma ligação a um nó inexistente nunca dispara (o fluxo `03` esteve assim desde 23/08). `test_n8n_guardas.py` verifica ambas.
- **WhatsApp não lê Markdown** — `channels/whatsapp/formatacao.py`, ponto único de saída. **Sem gráficos de evolução nem de receita** — os dados mentiriam (`dashboard-plano.md`).
- **Página ≠ OG tags em `imoveis.figueirahome.pt`**: o SPA renderiza os publicados, o *prerender* só serve OG tags a bots — `curl` não distingue, ir ao browser. **`preview_url` é `false` por omissão na Cloud API**: sem a chave o WhatsApp mostra o URL cru, em silêncio. Tem teste.
- **"Publicar apesar de indisponível" no eGO** mantém o imóvel na Web API sem nenhum campo o denunciar: `_existing_ego_ids` filtra `publicado=true`; sem isso o sync criava **51 tarefas falsas**.
- **`nome` nunca é identificador sozinho** — nem para criar cliente (`find_or_create_cliente` exige telefone ou email), nem para achar lead aberta (`_criar_lead_se_preciso`: telefone→email→`cliente_id`).
- **Duas tabelas `contactos`**: `public` (PK real `(nome, criado_em)`, `id` UNIQUE, `ego_link` UNIQUE) e `prospeccao` (PK `id`) — **qualificar sempre `public.contactos`**. Escrevem na `public` o nosso scraper (upsert por `ego_link`, `criado_em` = data de **alteração** do eGO por instrução do pipeline externo: cada edição muda a PK), o pipeline do Miguel (sem `ego_link`) e os assistentes. Das 28 483 linhas, 15 852 não têm `ego_link` e ~10 000 repetem uma das 12 631 que têm: a **canónica é a com `ego_link`**. Não "corrigir" a chave sem falar com o Miguel (P4).
- **`contacto_id` aponta a `contactos(id)`, nunca à PK composta**, e escreve-se só pelas RPCs. **O eGO manda os relatórios por email acima de ~1000 linhas** (fatiar). O relatório "tarefas todas" traz 1 linha por tarefa **mais** 1 por oportunidade associada: contam-se as linhas sem `Referência`. `tarefas`: `origem_lista` é ENUM (só `todas_as_colunas` é nosso), estado `pendente`/`concluida`, FK a `oportunidades`.
- **`notas` dispara IA em cada INSERT** (`tgr_classify_lead`/`tgr_extract_prefs` → edge functions via `net.http_post`; UPDATE não dispara). **`oportunidades` tem `BEFORE UPDATE` que carimba `atualizado_em`**: desligar em updates em massa.

### Dados

**Um projecto só**, `zphasvfopnbzwnaidsnw` — dados **e** Auth. `get_supabase()` é o único cliente (`supabase_url`+`supabase_secret_key`, chave nova `sb_secret_...`). **Migrations corridas à mão pelo utilizador** no editor SQL — explicar antes.
Três tabelas de leads, de propósito: **`leads`** (`0021`, genérica), `agente_leads` (morta desde 18/08, por apagar) e `leads_angariacao` (Make + consultora; liga a `contactos` por `(nome, criado_em)`).
**`oportunidades`/`contactos` são de fora do repo** — o portal do Miguel lê-as, e desde 23/08 a `social_imovel_stats` dele lê a nossa `visitas`. São o **único sítio** que responde a "quem já falou com esta lead?".

### Ambiente local

- Python `...\Python312\python.exe` · fly `C:\Users\joaoa\.fly\bin\flyctl.exe deploy --app <nome>` (de dentro de `backend/`, `scraper/` ou `crons/` — o Dockerfile/`fly.toml` vivem em cada um). Apps: `figueirahome-agentos`, `figueirahome-scraper`, `figueirahome-crons`. Supabase CLI só de leitura. `.env`/Fly: Supabase ✅, Anthropic ✅, OpenAI ✅, eGO API+CRM ✅, SCRAPER_* ✅, AUTOMACAO_SECRET ✅, Telnyx ❌, Meta ❌. Testes: `pytest backend/tests/` de `backend/` — **283**. Scraper, de `scraper/`: `python upsert.py`, `python mapping_todas_colunas.py`, `python tarefas.py` (auto-testes) e `python tarefas.py sync --dry`.

### Bloqueadores activos

| Item | Estado |
|---|---|
| **Chaves legacy desactivadas** | ⚠️ bloqueia portal do Miguel, Make, bundle das landing pages (fora do repo). Reactivar como stopgap é decisão por tomar |
| Segredos antigos no Fly (`SUPABASE_SERVICE_ROLE_KEY` etc.) | ⚠️ não removidos em nenhuma das 2 apps — por decisão do utilizador |
| `whatsapp_permissao` a `True` em **3 de 79** | ⚠️ é o gate do template; sem o Make a marcá-lo à entrada, não sai template e não há A1 |
| Telnyx — credenciais e número PT +351 | ❌ bloqueia a voz |

### Próximos passos

1. **Correr o backfill de `contacto_id`** (`docs/fases/contacto-id-backfill.sql`, passos 1-4; ver a amostra do passo 3 "nome"; fora dos syncs 03:37 e 05:07 UTC). 24 h depois: `COUNT(contacto_id)` não desce.
2. `git push` dos 2 commits locais (`contacto_id`).
3. Dar à Bárbara (A4) o contexto de `contactos` que a Inês já tem (`engine._contexto_recrutamento`, `tipo_contacto='vendedor'`).
4. Fundir duplicados em `contactos` e repontar `contacto_id` para a canónica — com o Miguel. 2.ª fase: `contacto_id` em `leads`/`leads_angariacao`/`agente_clientes`.
5. Investigar o `01` do n8n a disparar ~12h tarde (ver Bugs).
6. Decidir: reactivar chaves legacy do Supabase (stopgap) ou esperar cada consumidor externo migrar; depois remover os segredos antigos do Fly.
7. Importar `02`/`03` no n8n (`01` já testado) — apagar leads de teste antes; `docs/n8n/README.md`.
8. Actualizar `docs/database-schema.md` ("um projecto, não dois"; colunas novas de `contactos` e da `0046`).
9. `guards._JANELA_LEAD_DIAS = 30` esconde leads pausadas que só respondam depois — a Sandra pediu 60 dias, não alterado (`lead-pausa-resumo.md`).

## Decisões arquitecturais

**Texto completo e o porquê de cada uma: `docs/decisoes.md`.** Ler antes de mexer
na área respectiva — quase todas registam uma tentativa que já falhou ao vivo.

- **Um motor, N assistentes** — nunca N cópias do loop. Novo assistente = entrada no dict + linha em `agente_config` (INSERT, não deploy). A3 "Inês" e A4 "Bárbara" seguiram este padrão.
- **Subconjunto de tools por assistente é fronteira de segurança**, não organização (`consultar_*` só no `broker`). **Nunca deixar o `agente` vir do pedido num endpoint sem auth** — foi assim que `/api/broker/chat` deu acesso não autenticado ao `broker` até 31/08; o endpoint público do site (`/api/site/chat`) nunca aceita esse campo.
- **Router por regex, não por LLM**; routing **sticky** em `agente_conversas.agente`, sentido único A2→A1.
- **Regras que não podem falhar vivem em `guards.py`** (dedup + 80%), nunca no prompt. **Dedup: o nome é sempre tentado**, aceite só quando nada contradiz (`_compativel`).
- **Fallback de tipologia dentro da tool** (o modelo perdia moradias T2). **Tool forcing** na iteração 0 quando `_SEARCH_RE` bate; sem ele Claude prometia callbacks.
- **Assistentes nunca escrevem em `oportunidades`** — espelho do eGO, pipeline externo. A lead qualificada pára numa **tarefa** (+ email ao corretor): não há API de escrita do eGO. **Em `contactos` escrevem desde 21/09** (espelho aditivo, nunca mexe em linha que não seja sua).
- **Leads da Meta: semear a conversa, não mexer no router** — a resposta a um template é "Sim"/"Olá", que `_A1_RE` não apanha. **Recrutamento/angariação** não têm semeadura: `guards.agente_de_lead` cai em `contactos` por `tipo_contacto`, e o contexto (nome, template) vem de `contactos`.
- **`load_conversation` procura por variantes do número** — a Meta manda `351…`, a semeadura guarda 9 dígitos; com `.eq()` exacto a thread nunca era encontrada.
- **Qualificação: regra única em `guards.py`, dois gatilhos** — `find_or_create_cliente` e `promover_se_qualificada` (fim de turno). **`find_or_create_cliente` exige telefone ou email para criar**; `_criar_lead_se_preciso` desduplica por telefone→email→`cliente_id`.
- **Instrução específica de canal vive no motor (`engine._montar_system_prompt`)**, não no prompt base — pedir telefone só entra para o `site`. **Segredo de endpoint público falha ao pedido, nunca ao arranque** (`require_widget_key`).
- **Desfecho de conversa ≠ qualificação.** **`engano` fecha**; **`sem_resposta` e `pausa` ficam ABERTOS** (quem responde tarde mantém a Matilde e o `imovel_ref`); só o nudge trata `pausa` como fechada. Detecção por **tool**, escrita em código.
- **Os travões de envio são colunas, nunca o estado** — `follow_up_em` (`0030`) e `contacto_humano_em` (`0032`): o estado é editável no painel **e** reescrito pelo n8n. O painel manda um **booleano** e o servidor carimba (com um `datetime`, o `exclude_none` deixava marcar e não desmarcar).
- **Visitas em tabela própria (`visitas`, `0023`)** — o eGO dá uma linha por visita; `oportunidades` fica intacta (o portal do Miguel lê-a).
- **`contacto_id`: elo por RPC, FK ao `id`, canónica = `ego_link`; sync de tarefas = snapshot completo em fatias** (não "últimos N dias", senão as concluídas ficam `pendente` para sempre) — porquê em `docs/decisoes.md` ("`contacto_id` e sync de tarefas").
- **Segredo próprio para automações** (`X-Automacao-Secret`) — Make e n8n não têm de poder disparar syncs do eGO; segredo vazio nunca autentica.
- **Refs duplicadas do eGO desempatam por data de alteração**, não pela ordem da lista (FH2460 4D gravava piso 0 num 4.º andar).
- **O link da LP é uma tool, não uma frase no prompt** — diz ao modelo **"escreve"**, nunca "enviei", e proíbe asteriscos (ambos observados ao vivo). **Nunca recusar link por causa do formato da ref.** Procura por ref em `_por_referencia`.
- **Landing pages em HTML servido pelo backend**, não rota do SPA (OG tags no HTML). **`fonte_hash` decide se se regenera.** **`publicado` é coluna GENERATED**; `disponivel_na_api` é a excepção escrita pela app.
- **Sync eGO sempre full** (`?Since=` avariado). **Validação CRM completa só manual**, restrita aos refs que saíram da API e **depois do upsert, nunca antes** (à frente estourou o `--max-time` do cron). **RAM da app principal é escassa**: Playwright nunca lá (`scraper/` tem app própria); 512mb, em 256 o uvicorn morria por OOM.

## Bugs conhecidos

- **Da auditoria de 06/09, por corrigir** (`ficheiro:linha` no HTML): recibos de entrega descartados (A9); email só com MQL completo (A5); `_consultar_leads` do broker lê `agente_leads` morta (A1); `_procurar_cliente` pára na 1ª correspondência (A3); `find_or_create_cliente` escreve por cima de telefone/email (A4); `lead_aberta` só por telefone (A8); `contacto_humano_em` por lead, não por pessoa (A6); `03` a 48h vs 24h do doc (A7).
- **O `01` dispara ~12h depois da lead entrar**, desde 28/08. Como **16 das 17 respostas reais vieram na 1.ª hora**, isto chega para matar a conversão. Por investigar nas execuções do n8n. (O fluxo de Recrutamento dispara em ~12 s — medido a 29/09.)
- **A4 não recebe o contexto de `contactos`** (nome, template), como a Inês não recebia. **`contacto_id`**: ~10 oportunidades por sync ficam sem contacto (colisão `(nome, criado_em)` no upsert de `contactos`); a camada "nome" do backfill é de baixa confiança. **Tarefas** apagadas ou reagendadas no eGO fecham a linha antiga.
- **Sem `logging.basicConfig`**: a raiz fica em `WARNING`; `sent`/`delivered`/`read` do WhatsApp são invisíveis e só se inferem contando recibos.
- **`agente_leads` ainda existe**, vazia de uso desde 18/08. **Dedup de clientes sob carga**: um teste falhou e voltou a passar com o mesmo código — se aparecerem duplicados em produção, é por aqui.
- **Nudge da Matilde**: a resposta "diga-me só que não" não foi confirmada ao vivo a chamar `encerrar_lead`.
- **Agente de voz** (bloqueado por Telnyx): sem barge-in; sessões em memória perdidas em restart; race condition (`is_speaking` vs `call.speak.ended`); janelas fixas de 2 s sem VAD.

## Convenções

- **Python:** PEP 8, type hints, async. **React:** funcionais + hooks, sem classes. **Nomes:** código em inglês; UI em PT-PT. **DB:** português, snake_case.
- **Segredos:** nunca hardcoded. Só em `.env` / Fly.io secrets.
- ⚠️ **O repositório GitHub é PÚBLICO** (`imogermano-dotcom/figueirahome_agentOS`).
  Zero credenciais e zero dados de clientes: os telefones em código são todos `912345678`,
  os emails são placeholders, os `.env.example` só têm `YOUR_*`. **Material interno da agência
  não entra** (`kb-a1-vendedor.md` no `.gitignore`; `*.xlsx` também — exports do eGO com
  dados de clientes) **nem nomes reais de clientes/candidatos em código, testes ou docs**.
- **Excepção:** os templates das landing pages não usam Tailwind — CSS à mão, zero
  pedidos externos, porque a página abre a partir de um anúncio pago.

## Regras para o Claude Code

1. Ler `docs/PRD.md` antes de feature nova; `docs/database-schema.md` antes de
   tocar na DB; `docs/api-spec.md` antes de criar/alterar endpoints;
   `docs/decisoes.md` antes de contrariar uma decisão.
2. **Fase nova → plano em `docs/fases/<nome>-plano.md`, resumo em `-resumo.md`.
   Plano antes de código, sempre.** Uma fase de cada vez; 1.ª resposta = plano.
3. Manter este ficheiro actualizado. **Limite: 200 linhas** — o histórico vai
   para `docs/fases/`, as decisões para `docs/decisoes.md`.
4. Nunca inventar credenciais.
