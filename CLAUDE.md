# CLAUDE.md — Figueirahome Agent Call

> Contexto principal do projecto. Lido automaticamente em cada sessão.

## O que é

Plataforma de IA para agência imobiliária em Portugal:
1. **Assistentes** — **A1 "Matilde"** (compra/arrendamento), **A2 "Maria"** (recepção e encaminhamento), **A3 "Inês"** (recrutamento) e **A4 "Bárbara"** (angariação), em WhatsApp, no painel e no site público (`figueirahome.pt`).
2. **Agente de Voz** — atendimento telefónico (Telnyx, +351 233 060 000), a funcionar desde 19/10 (`docs/fases/voz-telnyx-resumo.md`); ainda é um agente à parte, a direção é ser um canal do motor.
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

Continuação do handoff de 29/09. Detalhe completo: `docs/fases/handoff-2026-10-03-resumo.md`. Sessão de 29/09 a 03/10: Inês corrigida, tarefas do eGO sincronizadas por cron, e `contacto_id` para relacionar as tabelas pelo ID do contacto (**backfill do histórico corrido a 05/10**).

- **Assistentes, 07–08/10 (deployado)** — nudge salta conversas com tarefa `escalar`; router apanha "vender"/"trabalhar convosco" (menu da Maria); WhatsApp nunca pede telefone (motor); **leads dos assistentes** nascem com `tipo`+contacto e promovem MQL (site incluído; só compra/arrendamento) — **backfill `leads-do-assistente-backfill.sql` por correr (utilizador)**; **nota de estado por tool de registo** (`guards.tools_ja_usadas` + `motivos_escalados` → system prompt; o `tool_use` não fica no histórico e 74% dos turnos após escalar repetiam as tools, 12 s): **medir** repetições <15%, cache e `sem_texto`=0 (`nota-de-estado-escalada-plano.md`, `estado-da-conversa-e-aviso-unico-plano.md`); turno vazio após tool de registo responde frase neutra, não "Ocorreu um erro"; **um aviso (tarefa+email) por pessoa em 24 h** em `_promover_lead` (3 leads abertas davam 3 emails ao Miguel). Router do site **não** alargado ("terra/garagem" servem a compra e a venda). **Escalada com informação nova (13/10)**: `_escalar_para_humano` acrescenta "Atualização às HH:MM" à tarefa pendente e manda email de atualização (antes o dedup descartava-a e a candidata ouvia "o responsável terá isso em conta"); turno vazio tenta primeiro uma chamada final com instrução de resposta antes da frase enlatada (`escalada-atualizacao-e-turno-vazio-plano.md`). **Medir**: `sem_texto` com frase enlatada a descer, e atualizações sem repetição de email. `scripts/monitorizar_encaminhamento.py`.
- **n8n Angariação/Recrutamento, 13/10 (editado ao vivo, fluxos fora do repo)** — o fluxo "template Angariação" lia/marcava `leads_angariacao` (tabela do Make) mas o RPC `lead_meta_angariacao` só grava em `contactos`: nunca marcava `template_enviado_em` (follow-ups mortos); agora lê/marca `contactos` por `meta_lead_id`. **`p_whatsapp_optin` era `length > 0`** (qualquer resposta, incl. "não…", dava `whatsapp_permissao=True`: 71/71 em recrutamento); agora `startsWith('sim')` nos 2 ramos do "Meta leads to supabase" — **`whatsapp_permissao` anterior a 13/10 não é fiável** (5 de recrutamento por rever na Meta). Recusa → email ao Miguel por Resend (nó "Avisar Miguel", credencial `Header Auth account 4`); **a compra só o tem desde 18/10** (antes a recusa era silenciosa: 4 compradores desde 13/10) e esse também vai à **consultora do imóvel** (`imoveis.angariador` → `profiles.email`, como `notificacoes._consultor_do_imovel`; provisório até o eGO; **o email da consultora só passou a chegar a 19/10**: `profiles` tem RLS e a credencial Supabase do n8n é pública, o nó devolvia vazio — agora lê por HTTP com a credencial de service_role do n8n). ⚠️ **Editar o n8n pela API e pela UI ao mesmo tempo repõe o rascunho antigo** (o tab aberto regrava): recarregar antes de gravar; só a versão *publicada* corre. Por confirmar com lead real "sim": `Ler lead` devolve a linha, template sai, `template_enviado_em` gravado. `tipos` do RPC angariação só `['Lead Meta']` (segmento está em `tipo_contacto`).
- **Lead de compra → eGO (20/10; RECUSA e 2 h LIGADAS)** — a recusa do WhatsApp cria a lead **logo** (n8n, a par do email; **ligada a 20/10**, `LEAD_COMPRA_EGO_DESDE=2026-10-20`, nó ativo, **confirmada a 24–25/10 com 2 recusas reais**: lead criada em segundos, verificada no eGO, email à consultora e ao Miguel) e a «sem resposta em 2 h» corre no cron `leads-compra-para-ego` (**ligado a 21/10**, de 10 em 10 min, **só cria das 9h às 20h de Lisboa**; fora disso devolve `fora_do_horario`; sem email extra; os follow-ups de WhatsApp mantêm-se). **Criação pela Web API** (`PUT websiteapi…/v1/Lead`, contrato do antigo Make; **exige `EML`**, devolve 200 sem id; a `InsertLead` da API nova precisa de `internetlead/insert`, em standby com o Miguel). `POST /api/leads/meta/{id}/recusou-whatsapp` (segredo próprio `X-N8N-Secret`) decide 4 casos (oportunidade ativa → não cria e avisa esse consultor; já na caixa; contacto antigo; sem histórico). **O `RID` (`imoveis.ego_id`) liga o imóvel se este for publicado e então o eGO atribui a lead ao `angariador` (testado 20/10, FH2584); sem imóvel ligado, atribui pela regra geral dele**. **Desde 21/10 cria-se pelo `InsertLead`** (`EGO_CRIAR_LEAD_POR=api`; `webapi` = `PUT /v1/Lead`, o antigo Make, por omissão no código e para reverter): origem 11 / sub-origem «Facebook campanha», `realestateId` da API, id devolvido; exige a permissão **483 `internetlead/insert`** no utilizador 92411 (ligada a 21/10 com `backend/scripts/ego_permissao_internetlead_insert.ps1 -DoEnv -Ligar`; as permissões vão no token: reiniciar a app) e **atribui à consultora do imóvel: `assignToSecurityUserId`, ou `securityUserId` se faltar; ⚠️ `securityUserId` sozinho é QUEM CRIOU o registo** (FH2584: a lead de teste foi para a pessoa errada). Sem atribuição a lead fica invisível: **nunca se cria sem responsável** (`sem_consultora`, não marca, o email diz «criar à mão»); na recusa o `imovel_ref` vem do n8n (query) ou do nome do anúncio (`FH2584_V1`), porque o RPC não o grava em `contactos` (21/10: a lead de uma recusa ficou sem imóvel nem consultora, por atribuir à mão). **`UpdateLead` funciona (22/10), com condições**: `PUT` com o corpo COMPLETO (o `GetLead` e o corpo usam nomes diferentes: `obs`/`observation`, `leadTypeId`/`typeId`…) porque **substitui a lead** (corpo só com o `id` apagou título, email e telefone; corpo com título/contactos vazios responde `0`). Usar `ego_api.atualizar_lead(id, **mudanças)`, que monta o corpo, confirma lendo e recusa se mudar algo mais (reatribuição testada). O utilizador 92411 tem `allowAssignLeads` (pode receber leads reais por distribuição). O `RID` da Web API liga o imóvel só se publicado; o `InsertLead` usa o id de backoffice e não depende disso. **Desligar:** apagar `LEAD_COMPRA_EGO_DESDE` no Fly (compara por dia: `criado_em` é `date`) e desativar o nó n8n; ⚠️ o n8n publica ao gravar e um separador antigo reverte o nó. O aviso da recusa só ia ao Miguel até 20/10 (`profiles` tem RLS; agora HTTP com a credencial de service_role). `lead-compra-para-ego-plano.md`.
- **Recibos de entrega do WhatsApp (16/10, deployado `1c307c9`; migration `0048` corrida)** — o `200` da Graph API não é entrega. O webhook (`channels/whatsapp/recibos.py`) grava em `contactos`: `whatsapp_entregue_em` (delivered/read), `whatsapp_falhou_em` + `whatsapp_erro_codigo` (só `failed` **131026**, a Meta não distingue "sem WhatsApp" de "inativo"); quem escreve limpa a marca; todas as linhas do telefone (duplicados), UPDATE por `id`, nunca levanta. **Fase 2 no n8n (editada ao vivo)**: 9 fluxos de envio (templates compra/angariação/recrutamento + follow-ups 24h/72h; o 72h da Matilde `HRSMT…` foi o último, a 18/10) têm `onError: continueErrorOutput` no envio → "Erro de número inválido?" → marca `whatsapp_falhou_em`; **qualquer outro erro vai a `Parar com erro` (falha à vista)**; os follow-ups filtram `whatsapp_falhou_em=is.null`. **A regex não apanhava o erro real (19–20/10)**: o 72h da Matilde falhou 2 dias porque um contacto com `telefone='00351…'` (o scraper do eGO reescreve assim) saía sem normalizar e o WhatsApp respondia «Bad request – Parameter value is not valid» (`json.error` só traz a 1.ª parte; a 2.ª está em `error.description`) → `Parar com erro` matava o lote. **Corrigido a 20/10 nos 9 fluxos**: `telefone_e164` só dígitos, sem `00`, `351`+9 dígitos (os 2 templates de angariação/recrutamento recebem-no tratado do pai), e a regex testa o item inteiro. **Confirmado a 21/10 11:00 UTC** (72h da Matilde: 5 contactos, 0 erros, o `00351…` saiu `351…`, 0 `whatsapp_falhou_em`). Cron `resumo-falhas-whatsapp` (email diário, 08:40 UTC) registado **`enabled: false`** — ligar depois de ver um recibo real. `recibos-whatsapp-plano.md`, `scripts/entrega_whatsapp.py`.
- **API do eGO (`api.egocrm.com`, 16/10) — só plano, nada implementado** — analisada só em leitura: oportunidades ativas 2 674 (+18 985 arquivadas), 3 397 tarefas pendentes legadas na BD que nenhum sync fecha, 310 tarefas sem ligação. Fases F0–F7 e decisões pendentes (migration `0049`) em `docs/fases/ego-api-plano.md`; `docs/eGO-api/ego-api.md` = procedimento e armadilhas (`api-1.json` fora do repo, `.gitignore`). Nunca `UpdateEntity`; escritas no eGO só com ordem expressa.
- **Fluxo 01 da compra só com `contactos` (15/10, n8n editado ao vivo; sem run executada)** — lê/marca `contactos` (não `leads`); consentimento pela resposta crua `startsWith('sim')` passada pelo "Meta leads to supabase" (com `imovel_ref`, que o RPC `lead_meta_compra` só grava em `leads`); `leads.estado` fica `nova`; Matilde lê o template de `contactos` com fallback a `leads` (`engine._contexto_inicial`, deploy `a89fc87`). Migration `0047` = `contactos.contacto_humano_em` (guarda do 01; **sem escritor** ainda). **Por correr**: SQL que copia o template das 3 leads de 13–15/10 para `contactos`; **por confirmar** com lead real. RPC `lead_meta_compra` continua a escrever em `leads` e `contactos`. `template-compra-contactos-plano.md`, caixa no `docs/n8n/README.md` (o JSON do 01 no repo é snapshot antigo).
- **Syncs do eGO parados 14–15/10 (corrigido a 15/10)** — o utilizador do CRM passou a ter **2 escritórios**: o POST de login devolve "Log on the client" (`<select name=ApplicationID>`) e o login "falhava"; oportunidades (03:37) e tarefas (05:07) sem correr 2 dias, **em silêncio** (só os sucessos iam para `agente_sync_log`). O login escolhe o escritório por nome (`EGOREALESTATE_CRM_OFFICE`, por omissão `FIGUEIRAHOME`; `scraper/ego_auth.py` e `egorealestate_crm._login`, cópias separadas). Já com login, o relatório todas-as-colunas deixava 325 tarefas por gravar: `tarefa_criado_em` (`date`) ia em dd/mm/aaaa cru e `tarefa_status` (enum `pendente`/`concluida`) em "Concluído" — corrigidos em `mapping_todas_colunas` (mesmo mapa de estados do `tarefas.py`, com teste). **Aviso de falha**: `notificacoes.falha_de_sync` (oportunidades, tarefas, imóveis-API) — falha do **cron** grava `<tipo>_erro` em `agente_sync_log` e manda email ao diretor + `ALERTAS_PARA` (secret do Fly `ALERTAS_PARA`, configurado a 16/10); falha manual só regista. Não apanha um cron que nem arranca. ⚠️ **A password do eGO apareceu numa saída de diagnóstico** (o HTML do 2.º passo repete-a no campo password): mudá-la e atualizar `EGOREALESTATE_CRM_PASSWORD` no scraper e no agentos.
- **`contacto_id` em `oportunidades`/`tarefas`/`notas`/`visitas` (01/10)** — migration `0046` (aplicada à mão) + RPCs `set_contacto_oportunidades`/`propagar_contacto_id`. O scraper grava `contactos` primeiro e liga por `ego_link`. **Backfill do histórico corrido a 05/10** (`docs/fases/contacto-id-backfill.sql`): **21 022/26 057 oportunidades ligadas** (telefone 11 263, nome 8 786, email 925, `ego_link` 48; 5 035 sem elo), tarefas 18 846/23 723, notas 83 137/103 721, visitas 1 515/1 789. Camada `nome` (baixa confiança) com 197 ligações desfeitas por email/telefone contraditório; reversível por `contacto_match='nome'`. `contacto-id-plano.md`.
- **Tarefas do eGO (30/09)** — `scraper/tarefas.py sync`: snapshot das 2192 activas em 4 fatias por data de criação, upsert em `tarefas`, fecha (`concluida`) as nossas `pendente` que saíram. Cron `sync-tarefas` 05:07 UTC (job 6): **correu sozinho 01, 02 e 03/10**. `tarefas-sync-plano.md`.
- **Propostas aceites (25/10, deployado `564e3f1`)** — o sync das oportunidades lê só as «Editado em > últimas 48 h» e aceitar/recusar uma proposta **não conta como edição** (VEN_22173, VEN_20521, VEN_20311 ficaram atrasadas; pedido #34 do Miguel). Cron `sync-propostas` 04:17 UTC → `POST /api/oportunidades/sync/propostas` (`reconciliar_propostas`): pergunta à API do eGO as oportunidades ativas com proposta (`ListOpportunityByPage` + `proposalMinDate` + `proposalStatusIDList`; **1 = Em avaliação, 3 = Aceite, 4 = Rejeitado**, deduzido por correspondência) e corrige só o `estado_proposta` que diverge; valor e data continuam a vir do relatório. Só ativas desde 2020. Linhas apagadas no eGO (VEN_22261, VEN_22277) continuam no Supabase (pedido #31 por fazer). `propostas-e-fim-de-conversa-resumo.md`.
- **Interesse real → lead no eGO (25/10, `8bf60e6`, LIGADO 21:31 UTC)** — quem **responde** à Matilde e mostra interesse (`pedir_visita` com sucesso, `escalar_para_humano` com motivo de compra, lead qualificada) é **marcado** (`contactos.interesse_real_*`, migration `0052`; só compradores Meta; a conversa nunca fala com o eGO) e o cron `leads-compra-para-ego` cria a lead (9h–20h, sem duplicar, nunca sem consultora), mesmo para quem já respondeu; OBS com o resumo. Interruptor `LEAD_INTERESSE_EGO` no Fly (vazio = nada se marca). Só daqui em diante: um comprador escalado antes foi marcado à mão a 25/10, **por ver a lead e se a pessoa antiga do eGO é reutilizada** (pedidos #47/#48). `lead-interesse-real-ego-plano.md`.
- **Inês só no concelho da Figueira da Foz (25/10, `4c52023`, pedido #33)** — secção «ZONA DE ACTUAÇÃO» em `_PROMPT_A3`: zona de fora ou mista → diz que só trabalhamos a Figueira, pergunta, **só escala depois de a pessoa aceitar** (ensaio com 9 situações, 0 escaladas de fora). Lista de freguesias do prompt é nossa, o Miguel ainda não a confirmou.
- **Imóveis de todos os estados (25/10, `c1edd03`, pedido #45)** — a Web API só dava os publicados (705 imóveis do eGO fora do Supabase, 7 com estado errado). `POST /api/imoveis/sync/egorealestate/todos` (`?dry=1` conta sem escrever; dry-run em produção deu 705 a inserir, 21 a atualizar) lê a `ListRealestateByPage` e insere com `disponivel_na_api=false` (**`publicado` é GENERATED: nunca publica**), atualiza só o que a Web API não vê e `fonte!='manual'`, nunca apaga. **1.ª passagem real por fazer (avisar o Miguel) e cron `sync-imoveis-todos` `enabled: false`.** As comissões **não vêm na API** (o eGO confirmou que ainda não as implementou, pedido #41). `imoveis-todos-os-estados-plano.md`.
- **Fim de conversa e recusa no WhatsApp (25–26/10, `e49d454`, `c89deba`)** — se a assistente já se despediu e a pessoa só manda emojis, «obrigado» ou «até logo», o motor devolve `""` e o webhook não envia (uma lead gerou ~40 trocas de carinhas). **A recusa fica em `contactos.nao_contactar_em` (migration `0053`)**: `encerrar_lead` grava-a mesmo sem linha em `leads` (angariação e recrutamento só vivem em `contactos`; foi o buraco do nudge à Bárbara, 24/10) e um opt-out explícito («não me contactem», «stop») marca-a em código. O nudge dos 3 assistentes verifica-a (falha fechado) e salta também agradecimentos e recusas curtas; **a marca bloqueia só envios proativos** (a cascata e a reativação, que não existem, terão de a ler). Detetores em `guards.py`. A regra «imóvel fora de Figueira da Foz é nosso» está no prompt `a1_vendedor` (`agente_config`, 22/10; **se a KB `kb-a1-vendedor.md` for recolada no painel, perde-se**).
- **Inês (A3), 29/09 (v106)** — recebe o contexto da candidatura Meta (`engine._contexto_recrutamento`); resposta sem texto já não vira "Ocorreu um erro" (`erro=sem_texto`); lead de recrutamento nasce `tipo='recrutamento'` e volta à Inês (`guards.agente_de_lead`); prompt sem pedir telefone no WhatsApp nem prometer prazos.
- **Atribuição Meta ads** (`ad_id`/`ad_name`/`adset_*`, `0045`) **testada com lead real (29/09)**, sem duplicar (`contactos-atribuicao-ads-resumo.md`). `telefone`/`telemovel` unificados em `contactos`; `oportunidades.cliente_telefone/email` espelhados do contacto.

### Produção

| Componente | Estado |
|---|---|
| `sync-tarefas` (cron 05:07 UTC) | ✅ a correr sozinho desde 01/10 |
| `contacto_id` (`0046`, scraper) | ✅ migration, scraper e backfill (05/10, 81% ligadas); confirmado após os syncs de 06/10 (21 022 mantido) |
| Atribuição Meta ads, Inês (A3, v106) | ✅ 29/09 |
| `Meta leads to supabase`, templates `01`/Angariação/Recrutamento (n8n) | ✅ 15/09–25/09 — testados com lead real |
| A1 `pedir_visita`, Nudge (A1/A3/A4), estado `pausa` | ✅ 18/09–28/09 |
| Backend/Scraper/Frontend/Crons | ✅ (03/10). `master` alinhado com `origin` (05/10) |

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
- **Duas tabelas `contactos`**: `public` (PK real `(nome, criado_em)`, `id` UNIQUE, `ego_link` UNIQUE) e `prospeccao` (PK `id`) — **qualificar sempre `public.contactos`**. Escrevem na `public` o nosso scraper (upsert por `ego_link`, `criado_em` = data de **alteração** do eGO por instrução do pipeline externo: cada edição muda a PK), o pipeline do Miguel (sem `ego_link`), os assistentes (`agente`), as RPCs `lead_meta_*` (`meta_lead_id`) e **os formulários do site** (confirmado 07/10: `tipos` `form`/`comprar`/`visita`/`property_detail`, sem `ego_link`, `imovel_ref` só no texto de `mensagem`, `whatsapp_permissao` sempre `False`, `origem` vazia; 16 linhas desde 09/07). Linhas sem `ego_link` e sem `agente`/`meta_lead_id` não vêm do nosso scraper (descarta-as). **A fusão de duplicados tem de ser re-executável**: o site e o eGO continuam a criar pessoas. Das 28 483 linhas, 15 852 não têm `ego_link` e ~10 000 repetem uma das 12 631 que têm: a **canónica é a com `ego_link`**. Não "corrigir" a chave sem falar com o Miguel (P4).
- **`contacto_id` aponta a `contactos(id)`, nunca à PK composta**, e escreve-se só pelas RPCs. **O eGO manda os relatórios por email acima de ~1000 linhas** (fatiar). O relatório "tarefas todas" traz 1 linha por tarefa **mais** 1 por oportunidade associada: contam-se as linhas sem `Referência`. `tarefas`: `origem_lista` é ENUM (só `todas_as_colunas` é nosso), estado `pendente`/`concluida`, FK a `oportunidades`.
- **`notas` dispara IA em cada INSERT** (`tgr_classify_lead`/`tgr_extract_prefs` → edge functions via `net.http_post`; UPDATE não dispara). **`oportunidades` tem `BEFORE UPDATE` que carimba `atualizado_em`**: desligar em updates em massa.

### Dados

**Um projecto só**, `zphasvfopnbzwnaidsnw` — dados **e** Auth. `get_supabase()` é o único cliente (`supabase_url`+`supabase_secret_key`, chave nova `sb_secret_...`). **Migrations corridas à mão pelo utilizador** no editor SQL — explicar antes.
Três tabelas de leads, de propósito: **`leads`** (`0021`, genérica), `agente_leads` (morta desde 18/08, por apagar) e `leads_angariacao` (Make + consultora; liga a `contactos` por `(nome, criado_em)`).
**`oportunidades`/`contactos` são de fora do repo** — o portal do Miguel lê-as, e desde 23/08 a `social_imovel_stats` dele lê a nossa `visitas`. São o **único sítio** que responde a "quem já falou com esta lead?".

### Ambiente local

- Python `...\Python312\python.exe` · fly `C:\Users\joaoa\.fly\bin\flyctl.exe deploy --app <nome>` (de dentro de `backend/`, `scraper/` ou `crons/` — o Dockerfile/`fly.toml` vivem em cada um). Apps: `figueirahome-agentos`, `figueirahome-scraper`, `figueirahome-crons`. Supabase CLI só de leitura. `.env`/Fly: Supabase ✅, Anthropic ✅, OpenAI ✅, eGO API+CRM ✅, SCRAPER_* ✅, AUTOMACAO_SECRET ✅, N8N_SECRET ✅, Telnyx ✅, Meta ❌. Testes: `pytest backend/tests/` de `backend/` — **525**. Scraper, de `scraper/`: `python upsert.py`, `python mapping_todas_colunas.py`, `python tarefas.py` (auto-testes) e `python tarefas.py sync --dry`.

### Bloqueadores activos

| Item | Estado |
|---|---|
| **Chaves legacy desactivadas** | ⚠️ bloqueia portal do Miguel, Make, bundle das landing pages (fora do repo). Reactivar como stopgap é decisão por tomar |
| Segredos antigos no Fly (`SUPABASE_SERVICE_ROLE_KEY` etc.) | ⚠️ não removidos em nenhuma das 2 apps — por decisão do utilizador |
| `whatsapp_permissao` a `True` em **3 de 79** | ⚠️ é o gate do template; sem o Make a marcá-lo à entrada, não sai template e não há A1 |
| Lead de compra → eGO (`InsertLead`) | ✅ recusa (20/10) e cron das 2 h (21/10, 9h–20h) vistos com leads reais a 22–25/10; a de quem responde com interesse real criada desde 25/10 (`LEAD_INTERESSE_EGO`), por ver com uma lead real |

### Próximos passos

1. Dar à Bárbara (A4) o contexto de `contactos` que a Inês já tem (`engine._contexto_recrutamento`, `tipo_contacto='vendedor'`).
2. Fundir duplicados em `contactos` e repontar `contacto_id` para a canónica — com o Miguel. 2.ª fase: `contacto_id` em `leads`/`leads_angariacao`/`agente_clientes`.
3. Decidir: reactivar chaves legacy do Supabase (stopgap) ou esperar cada consumidor externo migrar; depois remover os segredos antigos do Fly.
4. Importar `02`/`03` no n8n (`01` já testado) — só faz sentido com a campanha de compra reactivada; apagar leads de teste antes; `docs/n8n/README.md`.
5. `guards._JANELA_LEAD_DIAS = 30` esconde leads pausadas que só respondam depois — a Sandra pediu 60 dias, não alterado (`lead-pausa-resumo.md`).

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
- **Matilde sem leads novas da Meta** — a campanha de compra esteve **parada** (confirmado 06/10; retomada a 13/10: 3 leads até 15/10) e a última lead de compra entrou a 07/09. O "`01` a disparar ~12h tarde" **não se confirma**: nas 150 leads de compra com template a mediana é 0 h (~2 s), e os 7 atrasos >1h são de agosto (5 delas um lote de 28/08, à espera da aprovação do template). O `01` é subfluxo do "Meta leads to supabase" (webhook da Meta), sem nós de espera. 156 leads de compra (153 de agosto) nunca receberam template (`nova`); os follow-ups da Matilde estão inactivos no n8n.
- **A4 não recebe o contexto de `contactos`** (nome, template), como a Inês não recebia. **`contacto_id`**: ~10 oportunidades por sync ficam sem contacto (colisão `(nome, criado_em)` no upsert de `contactos`); a camada "nome" do backfill é de baixa confiança. **Tarefas** apagadas ou reagendadas no eGO fecham a linha antiga.
- **Sem `logging.basicConfig`**: a raiz fica em `WARNING`; `sent`/`delivered`/`read` do WhatsApp são invisíveis e só se inferem contando recibos.
- **`agente_leads` ainda existe**, vazia de uso desde 18/08. **Dedup de clientes sob carga**: um teste falhou e voltou a passar com o mesmo código — se aparecerem duplicados em produção, é por aqui.
- **Nudge da Matilde**: a resposta "diga-me só que não" não foi confirmada ao vivo a chamar `encerrar_lead`.
- **Agente de voz**: barge-in por testar (`VOZ_BARGE_IN`); sessões em memória perdidas em restart; ~1 em 3 respostas curtas ainda falha no STT.

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
