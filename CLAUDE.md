# CLAUDE.md — Figueirahome Agent Call

> Contexto principal do projecto. Lido automaticamente em cada sessão.

## O que é

Plataforma de IA para agência imobiliária em Portugal:
1. **Assistentes** — **A1 "Matilde"** (compra/arrendamento) e **A2 "Maria"** (recepção e encaminhamento), em WhatsApp, no painel e no site público (`figueirahome.pt`).
2. **Agente de Voz** — atendimento telefónico (Telnyx). Bloqueado por credenciais.
3. **Assistente Broker** — chat interno do corretor, leitura da BD. **Painel** React: clientes, imóveis, leads, métricas.

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
├── api/             ← clientes, imoveis, imoveis_sync, oportunidades_sync, leads,
│                      tarefas, config, dashboard, broker, agentes, landing ⑂,
│                      leads_meta (semeadura das leads da Meta — n8n)
├── landing/ ⑂       ← gerador.py (allowlist pública + hash + API) · templates/
├── agents/voice/    ← webhook Telnyx, audio_ws, save_call, claude_agent (só voz)
├── agents/broker/   ← engine (motor único), assistants, router, guards (dedup +
│                      80% + qualificação), custos, tools, conversation, nudge
│                      (lembrete 24h), channels/whatsapp/ (webhook, meta_api, formatacao)
├── integrations/    ← egorealestate.py (cliente API), imoveis_sync.py (upsert + extras)
├── db/supabase_client.py  ← get_supabase() [dados] + get_supabase_auth() [só login]
└── models/          ← Pydantic (imovel, cliente, lead, tarefa, ...)

frontend/src/  App.jsx · lib/ · components/ (Layout, Sidebar, AgenteMetricas, · AgenteConversas, Barras, LandingPagesTab ⑂, ui.jsx ⑂) · pages/ (Dashboard,  · Clientes, Imoveis, Leads, Chat, AgenteConfig, Config)
scraper/  app Fly.io separada, Playwright + upsert do eGO · cloudflare/ ⑂
```

**⑂ = só existe no ramo `feat/landing-pages`, não em `master`.**

## Estado actual — Handoff 2026-09-10

Sessão mista: auditoria continua parada, investigação ao vivo de um bug real no eGO, e uma fase nova completa — implementada, testada em produção e deployada (dois deploys: feature + fix pós-teste).

- **Nova feature em produção — Matilde, Frente A**: nudge dentro da janela de 24h quando a conversa pára a meio (Matilde sem resposta 6-20h), excluindo despedidas e leads fechadas/entregues a humano. Testado ao vivo com número real, cron activo (hora a hora) desde 09/09. Fix pós-teste: a guarda inicial excluía quem **nunca** teve `leads` (indistinguível de "fechada" via `lead_aberta`) — exactamente o caso de maior valor que motivou a fase (proposta de 110 000€ ao FH2571, sem nome/telefone recolhidos); `nudge._pode_enviar` só recusa com `ESTADOS_FECHADOS` ou `contacto_humano_em` explícitos. Detalhe: `docs/fases/matilde-followup-plano.md`/`-resumo.md`. Commits `093e414`/`d21eea0`.
- **Achado eGO, ao vivo**: `angariador` pode ficar congelado mesmo com sync sem erros — a Web API devolve `PropertyAgents: []` quando o eGO tem **múltiplos registos internos para a mesma referência** (`FH2483_A`: 3, só um exposto). Corrigido à mão (Sandra Silva); Miguel ficou de apagar o duplicado, **ainda não apagou**. De caminho, corrigida a memória do "bloqueio de carteira" do CRM (18/08): era **espaço de ID errado** (`ego_id` da Web API ≠ ID do backoffice), não permissão — `find_by_ref` já contorna, `validar_disponibilidade_crm` só ineficiente, não corrigido.
- **Auditoria de 06/09 continua parada** (pedido do utilizador, 07/09) — P0–P6 por decidir. Reunião com o Miguel em 07/09 tocou este tema; detalhe por colar (memória `reuniao-miguel-2026-09-07`).

### Produção

| Componente | Estado |
|---|---|
| Backend `figueirahome-agentos.fly.dev` | ✅ 2026-09-09, `d21eea0` — Matilde Frente A em produção |
| Frontend `figueirahome-agentos.pages.dev` | ✅ Cloudflare Pages, auto-deploy do push |
| Scraper `figueirahome-scraper.fly.dev` | ✅ 2026-08-15 em `7b1843f` |
| Assistentes A1/A2 | ✅ WhatsApp + painel, pesquisa real + link da landing page + nudge 24h |
| Cron imóveis (GitHub Actions) | ✅ `sync-imoveis.yml`, **06:00 e 13:00 UTC** |
| Cron oportunidades (GitHub Actions) | ✅ `sync-oportunidades.yml`, **03:00 UTC** |
| Cron nudge Matilde (GitHub Actions) | ✅ `nudge-matilde.yml`, **hora a hora**, desde 09/09 |
| n8n `01` | ✅ testado em produção 29/08 |
| n8n `02`/`03` | ⚠️ **por importar/publicar** — sem mudança desde 06/09 |
| `master` | ✅ pushed e deployado. Landing pages **fora** de `master`, no ramo `feat/landing-pages` |

### Fases anteriores — deployadas, detalhe em `docs/fases/`

- **Matilde: nudge 24h dentro da conversa (09/09)** — `matilde-followup-resumo.md`
- **Auditoria "Leads de Campanha" — matriz, 12 achados, planos P0–P6 (06/09)** — `handoff-2026-09-06-resumo.md`
- **Sync: origem cron/manual, painel de sync limpo (03–05/09)** — `handoff-2026-09-05-resumo.md`
- **Chat do site, dedupe de leads, lead sem contacto (01–02/09)** — `handoff-2026-09-02-resumo.md`
- **Auditoria ao A1, 4 bugs — pesquisa, MQL, notificações, dedupe WhatsApp (31/08)** — `handoff-2026-08-31-resumo.md`
- **Landing pages**: no ar em `imoveis.figueirahome.pt`, fora deste repo; construtor (`feat/landing-pages`) **parado por decisão do cliente**.

### Invariantes que não são óbvias a ler o código

- ⚠️ **`flyctl deploy` envia a árvore de trabalho, não o HEAD**, e o `.dockerignore` não exclui as landing pages: **fazer merge do `feat/landing-pages` antes de correr a `0020` põe `/lp/*` a dar 500**.
- **Features do imóvel ≠ zona envolvente** nas `FeatureTags` do eGO: `SWIMMING_POOLS`/`PROPERTY_NEAR_GARDENS` são "há na zona"; as do imóvel são `PROPERTY_HAS_POOL`/`PROPERTY_HAS_GARDEN`. A tag errada põe o A1 a afirmar ao comprador o que o imóvel não tem.
- **Upsert por lotes do PostgREST**: uma chave presente num só registo vira coluna e escreve NULL em todos os outros. Omitir a chave não protege — custou 40 coordenadas. Esparsos saem por `_map_extras`, UPDATE linha a linha. **`latitude`/`longitude` só com `HasGPSLocation=true`** (13/55): sem o flag o eGO devolve o centróide da zona (42 imóveis em 10 pontos). A guarda vive no `_gps`, mas a chave tem de ser escrita pelo **`_map_property`** — no `_map_extras`, que filtra nulos, impedia escrever e nunca apagava.
- **O eGO demora ~10 min** a expor um imóvel novo na Web API. **Prompt caching a 67%** — "Servido de cache" a zero havendo turnos multiplica o custo por 10.
- **O `ID` da Web API do eGO (`imoveis.ego_id`) não é o mesmo ID do backoffice** (`/egocore/realestate/{id}`) — passar o nosso `ego_id` lá devolve sempre "não pode consultar", indistinguível de bloqueio de permissão (confirmado 5/5 amostras, 09/09). Backoffice tem o seu próprio ID, obtido por `find_by_ref`/pesquisa por referência — nunca por `fetch_detail(ego_id)` directo. **Um imóvel pode ter vários registos internos na mesma referência** (`FH2483_A`: 3), só um exposto na Web API — se esse não tiver agente, `angariador` fica congelado (filtro de `None` em `_map_extras` nunca apaga).
- **Três allowlists são fronteiras de segurança**, todas com teste: `_TOOLS_INPUT_SEGURO`, `gerador.CAMPOS_PUBLICOS`, `_FEATURE_BOOLS`. **A quarta não se vê em Python**: o consentimento de WhatsApp vem de um *trigger* na base (`tgr_normaliza_aceita_whatsapp`, `0031`, vivo desde 20/08).
- **O repo não é a fonte de verdade única do esquema** — 59 entradas em `supabase_migrations` vieram da interface do Supabase. **`db push` proibido** (a `0001` aborta); CLI só de leitura. `supabase migration list` antes de confiar no `database-schema.md`.
- **MQL = orçamento + zona + tipo de interesse** (`guards.lead_qualificada`). **Imóveis contam-se por `publicado` (53)**, não `disponibilidade`. **A lead responde na 1.ª hora ou nunca** (16 de 17 reais, máx. 1,3 h) e **13 das 17 conversas foram ao fim-de-semana** — a premissa das 48h do follow-up não está confirmada.
- **Visitas de um imóvel contam-se por `visitas.visita_imovel_ref`**, nunca por `oportunidades.imovel_ref` — a segunda é o imóvel da *oportunidade* e perde quem visitou vindo de outra (FH2571: 7 contra 4). O painel não mostra visitas do eGO; `visitas_pendentes` no Dashboard vem de `agente_tarefas`.
- **`200 accepted` da Graph API NÃO é entrega.** É "aceite para envio". A entrega só se sabe pelos `statuses` do webhook, e o n8n marca `template_enviado_em` com base no 200 — durante 6 dias marcou 45 leads como contactadas que nunca receberam nada. Quando a Matilde emudecer, **ver a faturação da WABA antes de culpar o conteúdo**.
- **O n8n não valida nada do que lá se escreve.** Um nome de coluna trocado no `filterString` devolve linhas a mais em silêncio (daí as guardas repetidas no `IF`), e uma ligação apontada a um nó que não existe importa-se sem aviso e nunca dispara — foi assim que o fluxo `03` ficou desde 23/08 ligado a nada. `test_n8n_guardas.py` lê os JSON e verifica ambas.
- **WhatsApp não lê Markdown** — `channels/whatsapp/formatacao.py`, ponto único de saída. **Sem gráficos de evolução nem de receita** — os dados mentiriam (`dashboard-plano.md`).
- **Página ≠ OG tags em `imoveis.figueirahome.pt`.** O SPA renderiza os 54 publicados (lê a nossa `imoveis` por `eq`); o **prerender** só serve OG tags a bots, e só para refs simples. `curl` não distingue as duas e leva a concluir "não existe" — ir ao browser. Faltar prerender é cosmético: cartão genérico, link a funcionar. **`preview_url` é `false` por omissão na Cloud API** — sem a chave o WhatsApp mostra o URL cru e nem lê as OG tags; falha em silêncio (200, entregue) e custou um deploy. Tem teste.
- **"Publicar apesar de indisponível" no eGO**: um interruptor mantém o imóvel na Web API depois de indisponível — **nenhum dos 104 campos o denuncia**. `_existing_ego_ids` filtra `publicado=true`; sem isso o sync criava **51 tarefas falsas**.
- **`nome` nunca é identificador sozinho** — nem para criar cliente (`find_or_create_cliente` exige telefone ou email), nem para achar lead aberta (`_criar_lead_se_preciso` procura por telefone→email→`cliente_id`). Uma lead da Meta nasce sem `cliente_id`; só o ganha ao qualificar — raro.
- **`contactos` é escrita pelo nosso scraper** (`scraper/upsert.py`, upsert por `ego_link`) **e** por um pipeline de fora sem `ego_link`. PK real `(nome, criado_em)`; o scraper grava `criado_em` com a data de **alteração** do eGO, por instrução do pipeline externo — cada edição muda a PK. Não "corrigir" sem a query R2 e sem falar com o Miguel (P4). `telemovel` vai sem normalizar: é por isso que o telefone acha 54/281 e o email 232.

### Dados

Tudo no projecto `zphasvfopnbzwnaidsnw` (settings `supabase_imoveis_*`, CLI ligado
a ele); o original `fykbo…` é **só Auth** — lá só se lê a `profiles`, para o email
da consultora. `get_supabase()` = dados, `get_supabase_auth()` = login.
**Migrations corridas à mão pelo utilizador** no editor SQL — explicar antes.
Três tabelas de leads, de propósito: **`leads`** (`0021`, genérica — para aqui
convergiram as outras, `0029` deu-lhe `origem`), `agente_leads` (morta desde
18/08, por apagar) e `leads_angariacao` (79, Make + consultora).
**`oportunidades`/`contactos` são de fora do repo** — o portal do Miguel lê-as, e
desde 23/08 a `social_imovel_stats` dele lê a nossa `visitas`. São o **único
sítio** que responde a "quem já falou com esta lead?" (cruzar por telefone).

### Ambiente local

- Python `...\Python312\python.exe` · fly `C:\Users\joaoa\.fly\bin\flyctl.exe deploy --app <nome>` (correr de dentro de `backend/` — Dockerfile/`fly.toml` vivem lá, não na raiz) · Supabase CLI ligado ao projecto de dados (só leitura — ver decisões). `.env`/Fly: Supabase ✅, Anthropic ✅, OpenAI ✅, eGO API+CRM ✅, SCRAPER_* ✅, **AUTOMACAO_SECRET ✅** (09/09, Fly + GitHub Actions), Telnyx ❌, Meta ❌. Testes: `pytest backend/tests/` de `backend/` — **244**. Scraper: `python upsert.py` e `python mapping_todas_colunas.py` de `scraper/`

### Bloqueadores activos

| Item | Estado |
|---|---|
| **Portal do Miguel** | ⚠️ ainda em vigor, lê o mesmo Supabase. **Bloqueia a `0022`**: se usar a chave `anon`, apertar o RLS de `contactos`/`imoveis`/`oportunidades` parte-o. Confirmar a chave antes de correr |
| `whatsapp_permissao` a `True` em **3 de 79** | ⚠️ é o gate do template; sem o Make a marcá-lo à entrada, não sai template e não há A1. **Formulário de venda do Meta Lead Ads** ainda não existe: os alias em `_ALIAS_FICHA` são palpites tirados do de angariação |
| Telnyx — credenciais e número PT +351 | ❌ bloqueia a voz · ~3459 linhas `fonte='manual'` de origem desconhecida: parado a pedido do utilizador |

### Próximos passos

**Auditoria de 06/09 → planos P0–P6, ainda por decidir** (parada 07/09;
detalhe no HTML e nos planos em `docs/fases/`). Reunião com o Miguel de
07/09 pode alterar prioridades — colar aqui quando definido.

0. Confirmar se o Miguel apagou o duplicado `FH2483_A` (`ego_id` `26927326`) — ainda lá a 09/09.
1. Confirmar o 1º envio real do nudge da Matilde (`agente_sync_log`, `tipo='nudge_matilde'`) — só testado com 1 número.
2. Colar `docs/site-chat/widget.js` no `figueirahome.pt`, confirmar ao vivo widget → Worker → Fly.
3. Importar `02`/`03` no n8n (`01` já testado) — apagar leads de teste antes; passos em `docs/n8n/README.md`.
4. Reenviar as 45 leads, prazo **23/09** — confirmar antes quais das 8 (Alexandra/Alexsandra) já contactadas.
5. Varrer `leads` por duplicados antigos · "Validar CRM" manual no painel (12 imóveis em limbo).
6. Campos reais do formulário de venda (`_ALIAS_FICHA` é palpite) · chave do portal do Miguel → desbloqueia RLS `0022` · decidir as 70 do CRM sem "Disponível".
7. Retomar construtor de LPs quando o cliente decidir — aí apagar `agente_leads` e actualizar `landing.py:223`.
8. Passagem automática ao eGO (chave de integração) · A3/A4 (adiados) · dados a montante (`responsavel`/`data_criacao_iso`/`valor_negocio`).

## Decisões arquitecturais

**Texto completo e o porquê de cada uma: `docs/decisoes.md`.** Ler antes de mexer
na área respectiva — quase todas registam uma tentativa que já falhou ao vivo.

- **Um motor, N assistentes** — nunca N cópias do loop. A3/A4 = entrada no dict + linha em `agente_config`, que é **a tabela de assistentes** (acrescentar = INSERT, não deploy).
- **Subconjunto de tools por assistente é fronteira de segurança**, não organização (`consultar_*` só no `broker`). **Nunca deixar o `agente` vir do pedido num endpoint sem auth** — foi assim que `/api/broker/chat` deu acesso não autenticado ao `broker` até 31/08 (`v63`); o endpoint público do site (`/api/site/chat`) nunca aceita esse campo.
- **Router por regex, não por LLM**; routing **sticky** em `agente_conversas.agente`, sentido único A2→A1.
- **Regras que não podem falhar vivem em `guards.py`** (dedup + 80%), nunca no prompt. **Dedup: o nome é sempre tentado**, aceite só quando nada contradiz (`_compativel`).
- **Fallback de tipologia dentro da tool** — o modelo perdia moradias T2 ao traduzir "T2"→`natureza`. **Tool forcing** na iteração 0 quando `_SEARCH_RE` bate; sem ele Claude prometia callbacks.
- **Assistentes nunca escrevem em `oportunidades`/`contactos`** — espelho do eGO, pipeline externo. A lead qualificada pára numa **tarefa** (+ email ao corretor, `notificacoes.py`): não há API de escrita do eGO, e um insert nosso em `contactos` fica órfão.
- **Leads da Meta: semear a conversa, não mexer no router** — a resposta a um template é "Sim"/"Olá", que `_A1_RE` não apanha. A thread nasce com `agente='a1_vendedor'`; alargar o regex mandaria para o A1 toda a gente que diz "olá".
- **`load_conversation` procura por variantes do número** — a Meta manda `351…`, a semeadura guarda 9 dígitos. Com `.eq()` exacto a thread nunca era encontrada e a funcionalidade parecia instalada sem fazer nada.
- **Qualificação: regra única em `guards.py`, dois gatilhos** — `find_or_create_cliente` (escrita de cliente) e `promover_se_qualificada` (fim de turno). Sem o segundo, a lead cujo formulário já traz o MQL nunca era promovida. `nova` só conta como "respondeu" no segundo. **`find_or_create_cliente` exige telefone ou email para criar** (nome nunca sozinho, 02/09) e **`_criar_lead_se_preciso` desduplica por telefone→email→`cliente_id`**, nunca só `cliente_id` — uma lead da Meta nasce sem ele.
- **Instrução específica de canal vive no motor (`engine._montar_system_prompt`), não no prompt base do assistente** — pedir telefone é redundante no WhatsApp (já se sabe pelo canal); só entra para o `site`. **Segredo de endpoint público falha ao pedido, nunca ao arranque** (`require_widget_key`, mesmo padrão de `require_automacao_access`).
- **Desfecho de conversa ≠ qualificação** — os três da spec §2.2 entram **ao lado** do MQL, não por cima. **`engano` fecha** (sai de `_ESTADOS_LEAD_ABERTA`, entra em `ESTADOS_FECHADOS`); **`sem_resposta` fica ABERTO** apesar do nome — quem responde tarde tem de manter a Matilde e o `imovel_ref`. Detecção do engano por **tool**, escrita em código.
- **Os travões de envio são colunas, nunca o estado** — `follow_up_em` (`0030`) e `contacto_humano_em` (`0032`). O estado é editável no painel **e** reescrito pelo n8n a cada passo, portanto não segura nada. O `contacto_humano_em` trava só o que **nós** iniciamos; a Matilde responde na mesma a quem escreve. O painel manda um **booleano** e o servidor carimba: com um `datetime`, o `exclude_none` do `atualizar_lead` deixava marcar e não deixava desmarcar.
- **Visitas em tabela própria (`visitas`, `0023`)** — em colunas de `oportunidades` cabia 1 por oportunidade e o eGO dá uma linha por visita. `oportunidades` fica intacta: o portal do Miguel lê-a.
- **Segredo próprio para automações** (`X-Automacao-Secret`) — Make e n8n não têm de poder disparar syncs do eGO; segredo vazio nunca autentica.
- **Refs duplicadas do eGO desempatam por data de alteração**, não pela ordem da lista — a ordem escolhia a cópia por preencher (FH2460 4D gravava piso 0 num 4.º andar).
- **O link da LP é uma tool, não uma frase no prompt** — a tool confirma que o imóvel existe e está publicado, e codifica a ref. Diz ao modelo **"escreve"**, nunca "enviei", e proíbe asteriscos: com "enviei" prometia a página sem dar o endereço, e a regra `*assim*` colava-se ao URL — ambos observados ao vivo. **Nunca recusar link por causa do formato da ref**: essa regra existiu meio dia e mentiu ao cliente. Procura por ref em `_por_referencia`, ponto único.
- **Landing pages em HTML servido pelo backend**, não rota do SPA — as OG tags têm de existir no HTML (WhatsApp). **`fonte_hash` decide se se regenera.** **`publicado` é coluna GENERATED**; `disponivel_na_api` é a excepção escrita pela app.
- **Sync eGO sempre full** (`?Since=` avariado). **Validação CRM completa só manual** (no cron sobrepunha estados que a API já confirmava) — **excepto restrita aos refs que saíram da API**, e essa corre **depois do upsert, nunca antes**: raspa o backoffice inteiro, e à frente do upsert estourou o `--max-time` do cron e matou o sync dois dias seguidos. **RAM da app principal é escassa**: Playwright nunca lá (`scraper/` tem app própria), e o `fetch_all` do backoffice obrigou a subir de 256 para **512mb** — em 256 o uvicorn morria por OOM a meio do sync.

## Bugs conhecidos

- **Da auditoria de 06/09, por corrigir** (detalhe e `ficheiro:linha` no HTML): recibos de entrega descartados (A9); email só com MQL completo (A5); `_consultar_leads` do broker lê `agente_leads` morta (A1); `_procurar_cliente` pára na 1ª correspondência, ambiguidade invisível (A3); `find_or_create_cliente` escreve por cima de telefone/email (A4); `lead_aberta` só por telefone (A8); `contacto_humano_em` por lead, não por pessoa (A6); `03` a 48h vs 24h do doc (A7).
- **O `01` dispara ~12h depois da lead entrar**, desde 28/08 — em rajada de manhã em vez de na hora. Como **16 das 17 respostas reais vieram na 1.ª hora**, isto sozinho chega para matar a conversão. Por investigar nas execuções do n8n.
- **Sem `logging.basicConfig`**: a raiz fica em `WARNING`. O `ERROR` das falhas de entrega aparece; `sent`/`delivered`/`read` são invisíveis e só se inferem contando recibos.
- **`agente_leads` ainda existe**, vazia de uso desde 2026-08-18 — a confusão só acaba quando for apagada (Próximos passos 7).
- **Dedup de clientes sob carga**: teste falhou e voltou a passar com o mesmo código. Se aparecerem duplicados em produção, é por aqui.
- **Nudge da Matilde (09/09)**: resposta "diga-me só que não" ao nudge não foi confirmada ao vivo a chamar `encerrar_lead` — a lógica de desfecho já existe no motor, mas o caminho a partir desta mensagem em concreto não foi testado.
- **Agente de voz** (bloqueado por Telnyx, não se manifesta hoje): sem barge-in; sessões em memória, perdidas em restart; race condition (`is_speaking` vs `call.speak.ended`); janelas fixas de 2 s sem VAD.

*Fechados 31/08–02/09: pesquisa, MQL, notificações, tarefas/leads duplicadas, timestamp `03`, lead sem contacto — `docs/fases/handoff-2026-09-02-resumo.md`.*

## Convenções

- **Python:** PEP 8, type hints, async. **React:** funcionais + hooks, sem classes. **Nomes:** código em inglês; UI em PT-PT. **DB:** português, snake_case.
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
2. **Fase nova → plano em `docs/fases/<nome>-plano.md`, resumo em `-resumo.md`.
   Plano antes de código, sempre.** Uma fase de cada vez; 1.ª resposta = plano.
3. Manter este ficheiro actualizado. **Limite: 200 linhas** — o histórico vai
   para `docs/fases/`, as decisões para `docs/decisoes.md`.
4. Nunca inventar credenciais.
