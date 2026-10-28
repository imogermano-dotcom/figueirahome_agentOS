# API do eGO CRM (`api.egocrm.com`) — plano

> Fase nova. **Plano antes de código** (CLAUDE.md, regra 2). Origem: acesso à API nova do eGO a 16/10
> (`docs/eGO-api/ego-api.md` = procedimento e armadilhas; `docs/eGO-api/api-1.json` = OpenAPI, 806 operações).
> Tudo o que está abaixo como "medido" foi lido a 16/10 com **leituras apenas** (nenhuma escrita no eGO nem na BD).
> Nada aqui foi implementado.

## Porquê
O scraper do CRM (Playwright, login web) falhou em silêncio 14–15/10 por causa do passo de escolha de escritório e depois por
dois erros de gravação; depende de relatórios por email acima de ~1000 linhas e de HTML. A API devolve JSON paginado, com o
`id` de backoffice. Esta fase decide **o que passa a ler pela API**, **o que se limpa** e **o que (se alguma coisa) se escreve no eGO**.

## O que a API é (resumo do que importa)
- Base `https://api.egocrm.com`, Bearer JWT de 24 h. Login em dois passos: `POST /authentication/Authentication/Login`
  (devolve `applicationsAvailable`) e `GET .../LoginToApplication?applicationId=X`. A conta vê **2 agências**; a nossa é
  `FIGUEIRAHOME` (`applicationId` 6429, não é segredo). As credenciais são as do CRM que já temos (`EGOREALESTATE_CRM_*`).
- Cloudflare dá 403 ao User-Agent por omissão do Python. As listagens POST levam `?applicationId=X` na query.
- Armadilhas e o incidente do `UpdateEntity` (`rolesBitFlag`): ver `docs/eGO-api/ego-api.md`. **`Insert*` e `Delete*` nunca foram testados.**

## Medido a 16/10 (só leitura)

| Entidade | Endpoint | API | BD | Conclusão |
|---|---|---|---|---|
| Oportunidades | `POST /lead/Opportunity/ListOpportunityByPage` | `leadArchived=0`: 2 674; `1`: 18 985; `2`: 21 659 | 26 081 | Ligam por `name` = `oportunidade_ref` (o `id` da API ≠ `oportunidades.id`). 2 655 das 2 674 ativas existem na BD. As 23 426 "em falta" são **arquivadas**, não desaparecidas. ~4 440 linhas da BD (sem agência, lista "Ativas" antiga) a API não explica. |
| Tarefas | `POST /task/Task/ListTaskByPage` | 22 512 | 23 874 | Estados: 1 Pendente, 2 Concluído, 3 Cancelado, 4 Em Curso, 5 Não Aplicado, 6 Arquivada. Pendentes na API (1+4) 2 155 contra 2 113 do nosso sync (`todas_as_colunas`): bate (8 oportunidades diferem). |
| Visitas | `POST /realestate/Realestate/ListRealestateVisitFile` | por `leadIds` (200 → 353 fichas) | 1 791 | Só devolve com `visitRoadMapId` ou `leadIds`. Traz data, `leadId`, `realestateId`, `visitReference`, pontos, observações, `cancelled`, `notAttended`. |
| Imóveis | `POST /realestate/Realestate/ListRealestateByPage` | 5 161 (227 campos) | 4 467 | 4 452 refs em comum; 705 só na API; os 47 publicados da BD estão todos. O `id` da API é o de **backoffice**: `imoveis.ego_id` só coincide em 385/4 452. |
| Contactos | `GET /entity/Entity/ListEntityByApplication` | 17 774 entidades (78 MB numa resposta) | 12 661 com `ego_link` | **Todas** as 12 661 estão na API (o id é o do `…/person/<id>`); **5 113 só na API**. Trazem NIF/IBAN/data de nascimento (RGPD). |
| Leads | `POST /lead/Lead/ListLeadByPage` | 73 (todas ativas) | — | Fonte curta (as leads novas são promovidas a oportunidades); `potencialClientId` vem vazio. |
| Notas | `POST /note/Note/ListNotesByPage` | por objeto (`objectName` = enum `BusinessObject`, 3 = Lead) | — | Sem listagem global: ~21 000 chamadas para o histórico, ou só as alteradas. |

Achados que mudam decisões:
1. **A BD está limpa de oportunidades, suja de tarefas.** As oportunidades arquivadas são legítimas (o eGO esconde-as por omissão).
   Das 5 510 tarefas `pendente` na BD, **3 397 vêm das listas antigas `Ativas`/`Arquivadas`** (última criada a 16/06): nenhum sync as fecha
   (só trata `todas_as_colunas`), e em 578 a API já nem tem pendente na oportunidade. Qualquer contagem de "tarefas pendentes" sem
   filtro de origem está inflacionada (~5 500 contra ~2 150).
2. **310 tarefas (231 leads) sem ligação**: leads arquivadas com `isOpportunity: 2` que a listagem não devolve; 229 resolvem por
   `GetOpportunity` para `VEN_`/`CAP_`/`LLO_`, mas só 1 existe em `oportunidades` — e `tarefas` tem FK para `oportunidades`.
   186 das 310 são concluídas: impacto baixo.
3. 1 426 tarefas não são de oportunidade (imóveis 852, entidades 478, processos 70): hoje o scraper também não as trata.

## Âmbito e ordem (por risco crescente)

### F0 — Cliente da API (sem escritas)
- `backend/app/integrations/egocrm_api.py`: login em dois passos, cache do token (24 h), User-Agent de browser, repetição simples em 401/429,
  `applicationId` por configuração (`EGOCRM_APPLICATION_ID`, por omissão 6429; as credenciais são as que já existem).
- **Corre no `scraper/`**, não no agentos (RAM 512 MB; a resposta das entidades tem 78 MB). Se o agentos precisar de ler, só listagens paginadas.
- Testes com respostas simuladas (`httpx.MockTransport`); nenhum teste bate no eGO.

### F1 — Reconciliação de leitura (zero escritas)
- `scripts/ego_api_reconciliar.py`: repete as medições acima e escreve um relatório; corre à mão. Serve de linha de base e de medição
  contínua (diferença API/BD por entidade). Não usa PII no relatório (contagens e referências).

### F2 — Tarefas pela API
- Substitui `scraper/tarefas.py sync` e o ramo de tarefas do relatório "todas as colunas". Mesmo upsert (`oportunidade_ref`, título, prazo),
  mesmo mapa de estados (Em Curso/Pendente → `pendente`, Concluído → `concluida`; Cancelado/Não Aplicado/Arquivada **por decidir**, ver abaixo).
- Passa a ligar `oportunidade_ref` por `name` via mapa `id → name` de `ListOpportunityByPage?leadArchived=2` (+ `GetOpportunity` para os órfãos).
- Mantém "fecha as nossas `pendente` que saíram do snapshot". **Limpar as 3 397 pendentes legadas** fica **fora do código**: é um UPDATE de
  linhas que não são do nosso sync e o portal do Miguel lê a tabela — decisão e SQL (corrido por ti) depois de falar com ele.
- O snapshot da API (22 512) cabe em 46 páginas de 500.

### F3 — Oportunidades pela API
- Lê com `leadArchived=2`; grava o `id` da API e o estado de arquivada em colunas novas (**migration `0049`, corrida à mão**: `oportunidades.ego_api_id bigint`,
  `oportunidades.ego_arquivada boolean`) para os painéis filtrarem "ativas" sem apagar histórico.
- Respeita as invariantes: **upsert por lotes do PostgREST** (chave presente num só registo vira coluna e escreve NULL nos outros → escrita linha a linha
  ou RPC), `contacto_id` **só por RPC**, `BEFORE UPDATE` que carimba `atualizado_em` (desligar em updates em massa).
- O scraper de oportunidades continua a existir até a F3 igualar o que ele grava (preferências, `pref_*`, `visita_*`, colunas `xlsx_*`): a API tem 157 campos
  mas não foi mapeada coluna a coluna — **mapeamento obrigatório antes de desligar o scraper**.

### F4 — Visitas pela API
- `ListRealestateVisitFile` por lotes de 200 `leadIds` (≈9 chamadas para 1 659 leads), grava em `visitas` (`0023`). O `realestateId` (backoffice) dá o
  `visita_imovel_ref`. Medir primeiro: a API deverá ter >1 950 fichas e a BD 1 791 — explicar a diferença antes de gravar.

### F5 — Imóveis: id de backoffice
- Coluna nova `imoveis.ego_backoffice_id` (mesma migration) preenchida por `reference`. **Não** se mexe em `ego_id` (índice único da Web API).
- Desbloqueia `fetch_detail` (que hoje devolve "não pode consultar" quando se passa o id errado) e os 10 imóveis "invisíveis".
- Os 705 imóveis só na API (265 `CAS`, 192 `APA`, 70 `FH2…`, 32 `I99`, …) **não** entram na BD nesta fase; só se investigam os 70 `FH2…`.

### F6 — Contactos: só relatório
- As 5 113 entidades que não temos **não se importam** nesta fase: há a fusão de duplicados por fazer com o Miguel e `contactos` tem PK composta `(nome, criado_em)`.
- Se um dia se ler, **só nome, telefone, email e ids**; nunca NIF, IBAN, data de nascimento nem observações (`ego-api.md`, RGPD). Dados de saída do relatório: contagens.

### F7 — Escrita no eGO (fase à parte, depois de F1–F4 estáveis)
- Candidatas: `InsertTask` (só `subject` obrigatório) para a tarefa da lead qualificada, e `InsertNote` (`objectId`, `objectName`, `description`, `applicationId`).
- Isto **contraria** a decisão "assistentes nunca escrevem em `oportunidades`; a lead qualificada pára numa tarefa + email" (`docs/decisoes.md`) — só se
  decide com plano próprio. Primeiro teste: uma tarefa numa oportunidade de teste, com leitura antes e depois; **nunca `UpdateEntity`** (incidente de 14/10).

## O que não faz
- Não desliga o scraper de oportunidades/notas/visitas até cada peça ter paridade medida (F1 como critério).
- Não apaga nem fecha nada na BD; não importa entidades; não escreve no eGO.
- Não altera o portal do Miguel nem as tabelas que ele lê (só colunas novas, nullable).

## Decisões por tomar
1. **Estados de tarefa**: `Cancelado`, `Não Aplicado`, `Arquivada` (5 345, de leads arquivadas) → `concluida`? ignorar? hoje só há `pendente`/`concluida`.
2. **Limpeza das 3 397 pendentes legadas** (com o Miguel).
3. **As ~4 440 oportunidades sem agência** que a API não vê: manter como estão ou marcar.
4. **Migration `0049`** (`ego_api_id`, `ego_arquivada`, `ego_backoffice_id`) — corrida por ti no editor SQL, depois de eu explicar.
5. **F7**: se e quando os assistentes escrevem no eGO.
6. **Password do eGO**: mudada e aplicada a 28/10 (ver `ego-api-substituir-scrapers-plano.md`); por confirmar só n8n/Make.

## Testes
- `backend/tests/test_egocrm_api.py`: login em dois passos (com seleção de agência), User-Agent enviado, repetição em 401, paginação.
- Mapas de estado/tipo (tabela da API → vocabulário da BD) com os valores reais de 16/10.
- Ligação `name → oportunidade_ref` e o ramo dos órfãos (`GetOpportunity`).
- `scripts/ego_api_reconciliar.py` com `--dry`/resumo; sem rede nos testes.

## Medição depois de cada fase
Diferença API/BD por entidade (F1): tarefas pendentes canónicas = API ±1%, oportunidades ativas = 2 674 ±1%, visitas = API.

## Risco
Leituras: baixo (token de 24 h, 46 páginas por snapshot de tarefas). Escritas na BD: só F2–F5, por upsert linha a linha com testes; sem migrations destrutivas.
Escrita no eGO (F7): alto — não avança sem plano e sem ordem tua.

**Estado: plano escrito a 16/10, nada implementado.**
