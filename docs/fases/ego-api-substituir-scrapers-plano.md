# Substituir os scrapers do eGO pela API: plano

> 28/10/2026. **Plano antes de código** (CLAUDE.md, regra 2); nada implementado. Continua `ego-api-plano.md` (16/10), que mediu contagens;
> este mede **o que cada endpoint devolve em campos e se dá para sincronizar por incremento**. Tudo lido só em leitura, a 28/10 (nenhuma escrita no eGO nem na BD).
> Motivo imediato: o sync das oportunidades (relatório por Playwright) falhou em 27 e 28/10 (14 e 37 oportunidades recusadas pelo check, 180 e 492 notas por gravar); a API dá estado, notas e ids sem relatório.

## O que já usa a API (hoje)
`backend/app/integrations/ego_api.py`: leads abertas, `InsertLead`/`UpdateLead`, imóveis de todos os estados (`todos_os_imoveis`), estado das propostas, oportunidades ativas
(`refs_ativas`) e apagadas (`oportunidade_apagada`). Login em 2 passos, token em cache, User-Agent de browser. O que ainda corre por scraper: **oportunidades + notas + tarefas + visitas + contactos**
(relatório «todas as colunas» por Playwright, `scraper/`) e a **validação/detalhe de imóveis pelo CRM em HTML** (`egorealestate_crm.py`).

## Medido a 28/10

| Entidade | Endpoint | Resultado |
|---|---|---|
| Oportunidades | `POST /lead/Opportunity/ListOpportunityByPage` | 157 campos por linha (o `GetOpportunity` tem 144 e **não** traz 13 que a lista traz). `leadStage` 1/2/3 = Ativa/Ganha/Perdida: **acaba o estado «Criada»** que o relatório dava. `alterDate` serve de incremento, **mas propostas não o mexem** (VEN_22173). |
| Notas | `POST /note/Note/ListNotesByPage` | Precisa de `objectName` (3 = oportunidade) **e de `objectIds`**: sem ids dá HTTP 500. 200 oportunidades → 2 144 notas numa chamada de 0,7 s. Traz `id` estável, `description`, `createDate`/`alterDate`, `securityUserId`, `historicTypeId`, `fileList`. |
| Tarefas | `POST /task/Task/ListTaskByPage` (+ `GET ListTaskByLead`) | Filtros por criação (`minEventCreatedDate`), estado, objeto. `subject`, `body`, `dateStart/End`, `eventStatusId`, `ownerSecurityUserId`, `assignedSecurityUserId`, `isRescheduled`, `rescheduledDate`, `closeDate`, `objectId/objectName` (a oportunidade). |
| Visitas | `POST /realestate/Realestate/ListRealestateVisitFile` | Com `applicationId` no corpo e `leadIds` funciona (o 401 de 16/10 era a falta do `applicationId`). 200 leads em 0,5 s. `date`, `interested`, `positivePoints`, `negativePoints`, `observations`, `aboutBusiness`, `notAttended`, `cancelled`, `visitReference`, `realestateId`, `leadId`. |
| Contactos | `POST /entity/Entity/ListEntityByPage` com `minAlterDate` | **Funciona** (47 alterados desde 26/10): a nota de `ego-api.md` que dava 401 só vale para outras variantes. Liga à oportunidade por `POST /entity/Entity/ListEntityByLead` (`leadIds` → `leadID` + `id` da entidade). Traz NIF/IBAN: ler só nome, contactos, ids, datas. |
| Preferências | `GET /lead/Opportunity/ListOpportunityPreference?leadID=<um>` | Um pedido **por oportunidade** (`leadIDList` dá 400). `LocationSearch`, `NatureSearch`, `BusinessSearch`, `RoomMin`, `PriceMin/Max`, `lastSearchDate`… |
| Imóveis | `ListRealestateByPage` / `GetRealestate` | 227 campos (218 no `Get`). Já em uso (`todos_os_imoveis`). O `id` é o de backoffice. |

## Mapa de campos: o que o scraper grava e de onde viria

**Oportunidades (`oportunidades`)**
- **Diretos da lista:** `oportunidade_ref` ← `name`; `cliente_nome`/título ← `title`; `ego_data_criacao` ← `createDate`; `ego_editado_em` ← `alterDate`; `estado_fechado_em` ← `closedDate`;
  `oportunidade_estado` ← `leadStage` (+ `archived`, `fieldStatusId`); `origem`/`sub_origem` ← `leadOrigin`/`leadSubOrigin`; `tipo_oportunidade`/`tipo_pedido` ← `masterLeadType`/`leadType`;
  `probabilidade` ← `leadProbabilitySucess`; `imovel_ref` ← `realestateReference`; `responsavel` ← `assignToSecurityUserNames`; `equipa_responsavel` ← `responsibleTeams`;
  `valor_negocio` ← `businessFinalPrice`; `data_escritura` ← `businessExecutionDate`; `ponto_situacao`(+data) ← `situationPoint`/`situationPointAlterDate`; `motivo_transacao` ← `leadPurchaseReasonId` (tabela de referência).
- **Por derivação:** `imovel_natureza/distrito/concelho/freguesia/venda/preco` e `imovel_proprietario` ← o imóvel (`realestateId`, já temos os 5 163 por `todos_os_imoveis`); `url` ← construído a partir do `id`; `agencia*` ← constantes.
- **Campos em falta: resolvidos abaixo** (secção «Campos em falta das oportunidades»).
- **Preferências (`pref_*`):** ← `ListOpportunityPreference`, um pedido por oportunidade; gravar por RPC `bulk_update_prefs` como hoje.

**Notas (`notas`)** ← `ListNotesByPage`: `nota_texto` ← `description`, `nota_data_raw` ← `createDate`, `nota_autor` ← `securityUserId` (nome por `ListEmployees`), `nota_tipo` ← `historicTypeId`, `nota_anexos` ← `fileList`.
Hoje a chave é `(oportunidade_ref, nota_texto, nota_data_raw)`; com a API passa a haver o `id` da nota (coluna nova `nota_ego_id`) e acabam as notas duplicadas por texto repetido.

**Tarefas (`tarefas`)**: `tarefa_titulo` ← `subject`, `tarefa_descricao` ← `body`, `tarefa_due_raw` ← `dateStart`, `tarefa_status` ← `eventStatusId` (mesmo mapa de `tarefas.py`), `tarefa_criado_em` ← `createdDate`,
`tarefa_responsavel` ← `assignedSecurityUserId`, `tarefa_criado_por` ← `ownerSecurityUserId`, `tarefa_reagendada` ← `isRescheduled`. A ligação à oportunidade é `objectId` (mapa `id → name`).

**Visitas (`visitas`)**: todos os 12 campos `visita_*` têm correspondente direto (tabela acima); `visita_imovel_ref` ← `realestateId` → imóvel; `visita_cliente` ← `potencialClientName`; `visita_responsavel` ← `ownerName`/utilizador.

**Contactos (`contactos`)**: `ego_link` ← `…/person/<id da entidade>`, `nome` ← `firstName`+`lastName`, telefone/email ← `personalContacts` (classificar pelo formato do valor, `ego-api.md`), `ego_atualizado_em` ← `alterDate`.
**Invariante a respeitar:** `criado_em` = data de **alteração** por instrução do pipeline externo (a PK é `(nome, criado_em)`); não mudar sem falar com o Miguel.

**Imóveis**: já em grande parte API. Falta trocar `egorealestate_crm.fetch_all/fetch_detail/find_by_ref` (HTML) por `ListRealestateByPage`/`GetRealestate` com o `id` de backoffice, e guardar esse `id` (`imoveis.ego_backoffice_id`).
As comissões aparecem como campos (`commissionSale*`) mas o eGO disse que não as implementou na API (pedido #41): **confirmar se vêm preenchidas antes de as usar**.

**Leads**: nada a substituir (`ListLeadByPage` e `InsertLead` já são API).

## Campos em falta das oportunidades (aprofundado a 28/10, só leitura)

Primeiro, quanto pesam: nas 1 000 oportunidades ativas da BD, `checklist_*`, `etapas_cpcv/escrituras`, `diferenca`, `valor_negocio` e `equipa_responsavel` estão **vazios em todas** (0 de 1 000): não há nada a substituir.
Preenchidos: `etapa_atual` 827, `imovel_proprietario` 838, `portal` 395, `data_proposta`/`proposta`/`estado_proposta`/`imovel_preco` 16, `data_escritura` 8, `probabilidade` 8, `etapa_proposta` 2, `motivo_transacao` 1.

| Campo | Resultado |
|---|---|
| `etapa_atual` | **Resolvido.** `ListOpportunityByPageIsReport` (mesmo corpo da lista) acrescenta `timelineName`: `[PT-PT]8-Fecho[/PT-PT]` = «8-Fecho» da BD, `…4-Qualificação…` = «4-Qualificação» (2 de 2 iguais). Tirar a marca `[PT-PT]…[/PT-PT]`. O histórico das etapas vem em `timelineList` (datas de entrada). |
| `data_proposta` | **Resolvido, com truque.** Não é um campo: o filtro `proposalMinDate`/`proposalMaxDate` da lista devolve as oportunidades com proposta nessa janela. Janela de um dia: VEN_22232 em 28/09 e VEN_22173 em 18/09, as duas datas da BD. Basta uma janela por dia (ou bisseção) para as ~16 ativas. `proposalMinAlterDate` filtra por **alteração da proposta**: resolve de vez o problema das propostas aceites/recusadas que não mexem no `alterDate`. |
| `estado_proposta` | Já resolvido (`estados_de_proposta`, 1/3/4). |
| `proposta` (valor) | **Não encontrado.** Não está na lista, no `GetOpportunity` (144 campos), nem no imóvel (`businesses[].prices` dá só o preço pedido, 313 000, não os 308 000 da proposta). A especificação não tem endpoint de propostas de venda (só `FinancialInstitutionProposal*`, que são de crédito). Pesa 16 oportunidades ativas. |
| `etapa_proposta` | **Não encontrado** (2 oportunidades; a BD tem `cpcv`). Provavelmente deriva da etapa da oportunidade; por confirmar. |
| `imovel_preco` | Resolvido: `realestate.businesses[].prices[].value` (313 000 = BD). |
| `portal` | **Parcial.** `portalId` 700 = «Idealista PT» vem nas recentes (VEN_22164, 22172, 22168), mas as antigas («SUPERCASA», «Página Web», VEN_11978…) voltam `None`. A BD fica com o valor antigo se a API não o der (não sobrescrever com nulo). |
| `imovel_proprietario` | **Derivável.** `ownerName` da lista vem vazio; o dono é a entidade do imóvel (`ListEntityByRealestate` ou `entityId` do imóvel + mapa de entidades). |
| `probabilidade`, `data_escritura`, `motivo_transacao` | Diretos: `leadProbabilitySucess`/`closeProbability`, `businessExecutionDate`, `leadPurchaseReasonId` (tabela `ListLeadPurchaseReason`). |
| `cliente_nome`, ligação ao contacto | `potencialClientId` vem preenchido nas oportunidades normais (45445619 em VEN_22232) = id da pessoa (o `ego_link`); nas leads recém-promovidas pode vir vazio. `ListEntityByLead` cobre os dois casos. |

**Sobra, na prática, uma única coisa sem substituto: o valor da proposta (`proposta`), 16 oportunidades.** Opções: manter só essa coluna pelo relatório; pedir ao eGO o endpoint (como a das comissões, #41); ou aceitar nula e mostrar o estado e a data, que a API dá.

## Como sincronizar por incremento (sem o relatório das 48 h)
1. Lista de ativas (`leadArchived=0`, ~2 700 linhas, uma a duas páginas) de cada vez: comparar `alterDate` com o guardado → só as alteradas vão ao `GetOpportunity`/preferências.
2. **Notas, visitas e tarefas das ativas lêem-se sempre**, sem depender do `alterDate`: lotes de 200 `leadIds` (≈14 chamadas, ~10 s no total). Foi isso que falhou nas propostas (editar não conta como edição).
3. Contactos: `ListEntityByPage` com `minAlterDate`; ligação por `ListEntityByLead` dos `leadIds` alterados.
4. Imóveis: como hoje (`todos_os_imoveis` + Web API), sem HTML.

Prova de que isto resolve o buraco de hoje: das 200 oportunidades ativas lidas, as recém-criadas (CAP_22364, VEN_22355, CAP_22174, LLO_22353) têm 1–6 notas na API e **0 na BD**. (Outras diferenças que vi não valem: a minha leitura da BD estava limitada a 2 000 linhas.)

## Fases (risco crescente; uma de cada vez)
| Fase | O quê | Critério de paridade |
|---|---|---|
| A1 | Cliente de leitura no `scraper/` ou módulo à parte: listas paginadas, lotes de ids, repetição em 401/429. Sem escritas. | Testes com `httpx.MockTransport`; nenhum bate no eGO. |
| A2 | **Notas** pela API (coluna `nota_ego_id`, migration à mão). Corre em paralelo ao scraper, em modo `--dry`, e compara. | Notas da API ⊇ notas da BD para as ativas; as 672 em falta de 27–28/10 aparecem. |
| A3 | **Tarefas** pela API (já planeado em F2 de 16/10). | Pendentes = API ±1 %. |
| A4 | **Visitas** pela API. | API ⊇ 1 791 da BD (explicar a diferença antes de gravar). |
| A5 | **Oportunidades**: campos diretos + derivados; `proposta` (valor) é a única coluna sem fonte na API (secção «Campos em falta»). Mapeamento coluna a coluna obrigatório antes de desligar. | Zero linhas ignoradas; estado = `leadStage`; comparação linha a linha com o relatório durante 1 semana. |
| A6 | **Contactos** por incremento + `ListEntityByLead`. | `ego_link` e telefone iguais aos do relatório nas alteradas. |
| A7 | **Imóveis** sem HTML (`GetRealestate` por id de backoffice). | Os 10 imóveis «invisíveis» e o `fetch_detail` deixam de falhar. |
| A8 | Desligar Playwright e o relatório (só depois de A2–A7 estáveis um mês). | RAM do scraper e `egorealestate_crm.py` removidos. |

## O que não muda / riscos
- **Upsert por lotes do PostgREST**: uma chave presente só em alguns registos escreve NULL nos outros; `contacto_id` só por RPC; `oportunidades` tem `BEFORE UPDATE` que carimba `atualizado_em`. A API tem campos esparsos, por isso as mesmas regras (escrita linha a linha ou RPC).
- **RGPD:** as entidades trazem NIF, IBAN e data de nascimento; ler e guardar só o necessário. Nunca `UpdateEntity`.
- **Password do eGO:** mudada a 28/10 (tinha aparecido numa saída de diagnóstico a 15/10). Aplicada em `figueirahome-agentos` e `figueirahome-scraper` (segredo `EGOREALESTATE_CRM_PASSWORD`) e testada em leitura: login da API (86 leads abertas) e login do CRM web do scraper. A API usa a mesma conta. **Por confirmar:** n8n, Make ou outra ferramenta que faça login com esta conta e ainda tenha a antiga.
- **Cloudflare/token:** User-Agent de browser, token de 24 h, `applicationId` em query ou corpo conforme o endpoint (a falta dele deu o 401 das visitas).
- O portal do Miguel lê `oportunidades`/`contactos`: só colunas novas, nulas por omissão; nada se apaga.
- O que a API mede e o relatório não: oportunidades **apagadas** (`fieldStatusId`) e **arquivadas**; o relatório mostrava só «Ativas».

## Decisões para ti
1. Começar por **A2 (notas)**: é a que está partida hoje e a de menor risco (acrescenta, não substitui).
2. Migration nova (`nota_ego_id`, depois `ego_api_id`, `ego_arquivada`, `ego_backoffice_id`): explico e corres tu no editor SQL.
3. Estados de tarefa `Cancelado`/`Não Aplicado`/`Arquivada` e a limpeza das 3 397 pendentes legadas (herdadas do plano de 16/10).
4. O valor da proposta (`proposta`, 16 ativas) não existe na API: manter o relatório só para essa coluna, pedi-lo ao eGO ou aceitar nula.
