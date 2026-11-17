# Tarefas pela API do eGO — F2 do `ego-api-plano.md` (17/11)

## Problema
O `sync-tarefas` (05:07 UTC) descarrega o relatório «tarefas todas» com Playwright, em 4 fatias de data (≤900 linhas, o eGO manda por email
acima de ~1000), ~150 s, ~2 114 linhas por run. É o sync mais frágil que resta: o login multi-escritório parou-o 2 dias em silêncio (14–15/10)
e depende da interface web. A API do eGO já devolve as tarefas (`POST /task/Task/ListTaskByPage`) e o resto dos syncs (propostas, imóveis,
leads) já corre por ela com `backend/app/integrations/ego_api.py`.

## Decisão
Ler as tarefas **pendentes** pela API, no agentos, e manter o resto do sync igual: mesmo upsert, mesma chave, «fecha as nossas `pendente` que
saíram do snapshot», mesmo `propagar_contacto_id`. Só muda a fonte.

- **Onde corre:** `ego_api.py` (agentos), não no `scraper/`. O receio de RAM do plano de 16/10 era a listagem de entidades (78 MB); as tarefas
  vêm paginadas (500 por página, ~46 páginas para as 22 512) e só se guardam as pendentes (~2 150).
- **Estados:** o snapshot é só `Pendente` (1) e `Em Curso` (4), como hoje. `Cancelado`, `Não Aplicado` e `Arquivada` **não se importam**: se uma
  das nossas `pendente` passa a um deles, deixa de estar no snapshot e fecha-se como `concluida` (o que o sync já faz). Isto resolve a decisão 1
  do plano-mãe sem novo valor no enum `tarefa_status`.
- **Interruptor:** `TAREFAS_VIA_API` no Fly (vazio = relatório, como hoje). O endpoint de tarefas existente em `api/oportunidades_sync.py`
  escolhe a via; **o cron não muda** e reverter é apagar o segredo. O scraper de tarefas fica intacto até à observação (F2.4).

## Fases
**F2.0 — Medir, só leitura (sem código de produção).** `scripts/ego_api_tarefas_comparar.py`, corrido à mão: lê as pendentes pela API e
compara com o snapshot do relatório de hoje e com `tarefas` (origem `todas_as_colunas`). Responde, com contagens e referências (sem texto de
tarefas):
1. Que corpo/filtro aceita `ListTaskByPage` para trazer só estados 1 e 4 (se não houver filtro, lê-se tudo e filtra-se do lado de cá).
2. De que campo vem cada coluna escrita hoje (`ego-api.md`/`api-1.json`, não inventar nomes): `oportunidade_ref` (a API dá o id; ligar por
   `name` via mapa `id → name` das oportunidades, com `GetOpportunity` para os órfãos), título, descrição, data de agendamento, responsável,
   criado por, estado, data de criação, reagendamento, tipo de negócio, link.
3. **Formato da chave.** A chave de upsert é `(oportunidade_ref, tarefa_titulo, tarefa_due_raw)` e o `tarefa_due_raw` guardado é a data do
   relatório em `dd/mm/aaaa`. A API dá data/hora: tem de converter-se para a **mesma string** (data de Lisboa), senão a 1.ª passagem duplica
   ~2 100 linhas. Verificar em amostra que a conversão reproduz a chave existente em 100% antes de avançar.
4. `Responsável` e `Criado por`: se a API só der ids de utilizador, ver se há listagem id → nome; sem ela a coluna degrada e é decisão tua.
5. Diferença API/BD: o plano-mãe mediu 2 155 pendentes na API contra 2 113 nossas (8 oportunidades diferem). Explicar cada diferença.

**Resultado da F2.0 (17/11, `scripts/ego_api_tarefas_comparar.py`, só leitura).** Pendentes API 2 113 (todas `Em Curso`, estado 4; `Pendente` = 0) contra 2 049 nossas:
- **Paridade da chave: 2 049/2 049 (100%)**, 0 só na BD, 33 só na API (oportunidades que não existem em `oportunidades`: FK, ficam saltadas).
- `eventStatusIds` filtra. A resposta é `searchList`/`searchCount` (não `totalRows`). Contagens por estado: Concluído 15 260, Arquivada 5 345, Não Aplicado 1.
- `tarefa_titulo` é o **nome do tipo** (`ListTaskType`, `name["PT-PT"]`, 33 tipos, os 13 usados têm nome), não o `subject`; o `subject` é a descrição (98,5% iguais).
- `dateStart` vem **sem fuso e em UTC**: converter para Lisboa (`T23:00:00` no verão é o dia seguinte). Sem a conversão só 1 134 de 1 883 chaves batem.
- `objectName` vem em texto (`Lead`). As 126 tarefas de roteiro de visitas (`VisitRoadMap`) trazem a lead em `objectSecondaryId`. Há 32 ids de lead fora da listagem, todos resolvidos por `GetOpportunity` (com 429: espera de 60 s). 25 tarefas sem lead (imóveis 5, entidades 18, processos 2).
- Responsável, criado em e data de agendamento: 100%. **Por tratar na F2.1:** descrição (31 diferem), criado por (85 diferem: `ListEmployees` dá só 15 utilizadores, falta o resto) e reagendamento (84 diferem).
- Legadas 3 397: 671 estão em oportunidades sem nenhuma pendente na API (candidatas à limpeza); as outras 2 726 precisam de comparação por tarefa.

**Os 3 campos secundários (17/11):** *criado por* — as 85 diferenças são 4 utilizadores que já não estão em `ListEmployees` (`GetSecurityUser` dá 404): sem nome não se escreve a coluna e a linha existente mantém o valor. *Reagendamento* — as 84 eram todas um dia à frente: `rescheduledDate` usa-se tal como vem (236/236). *Descrição* — 29 das 31 só diferem em pontuação/símbolos que o relatório perde; a API é a fiel, a 1.ª passagem corrige-as.

**F2.1 — feita (17/11, por commitar).** `ego_api.py`: `tarefas_pendentes`, `tipos_de_tarefa`, `utilizadores`, `refs_de_leads` (arquivadas por páginas, só `id`+`name`, para a RAM do agentos; o resto por `GetOpportunity`, máx. 60) e `_com_espera` (429: espera 65 s). `integrations/tarefas_api.py`: mapeamento puro e `snapshot()`. `cliente_nome`, `tipo_oportunidade` e `url` copiam-se da linha de `oportunidades` no sync (F2.2), como o relatório faz. `tests/test_tarefas_api.py`: 21 testes, suíte 888 verdes.

**F2.1 — Módulo e mapeamento (o que era o plano).** `ego_api.tarefas_pendentes()` (paginado, levanta se vierem menos linhas que o `totalRows`, como
`todos_os_imoveis`) e um mapeador API → registo de `tarefas` que devolve exatamente as chaves de `scraper/tarefas.map_row`. Testes com
respostas simuladas e os valores reais de estado e data observados na F2.0.

**F2.2 — Sync e endpoint em ensaio.** Função `sync_tarefas_api(dry=True)` que faz o mesmo que `tarefas.run`: snapshot, salta as sem `oportunidade_ref`
na BD (FK `tarefas_oportunidade_ref_fkey`; conta-as), upsert, fecha as nossas que saíram, `propagar_contacto_id`. `dry` devolve contagens
(a inserir, a atualizar, a fechar) sem escrever. Resumo com as mesmas chaves de hoje (`activas`, `com_ref`, `gravadas`, `fechadas`, `contacto_id`)
mais `via: "api"`, no mesmo `tipo` `egorealestate_tarefas` (a `/verificacao-diaria` e o aviso `falha_de_sync` continuam a servir).

**F2.3 — Ligar.** Com o dry-run a bater com o relatório (a inserir ≈ 0, a fechar ≈ as 3/dia habituais), correr uma vez à mão (**ordem tua**),
comparar, e só depois ligar `TAREFAS_VIA_API=1` no Fly. Segredos pelo dashboard ficam *Staged* até `flyctl secrets deploy`.

**F2.4 — Observar e retirar.** 5 dias de cron sozinho, comparando contagens com o dia anterior. Só depois, e como decisão separada, tirar
`scraper/tarefas.py sync`, o `/run/tarefas` e a fatia de tarefas do scraper.

## Travões (para nunca fechar o que não devia)
- Snapshot incompleto (menos linhas que o `totalRows`) → aborta antes de escrever. Nunca se fecha com dados parciais.
- Se o sync fosse fechar mais de max(50, 5%) das nossas abertas, aborta e avisa por email (hoje fecha 3 por dia). Limiar a ajustar com a F2.0.
- Falha do cron → `<tipo>_erro` em `agente_sync_log` + email, como `notificacoes.falha_de_sync` já faz.
- Fecha só `origem_lista='todas_as_colunas'` e `pendente`, como hoje. Nunca toca em linhas de outras origens.

## Fora do âmbito
- **As 3 397 pendentes legadas** (`Ativas`/`Arquivadas`, última criada a 16/06, nenhum sync as fecha): fora do código. A F2.0 produz a lista em
  contagens (quantas a API já não tem pendentes); o UPDATE, se houver, é SQL corrido por ti depois de falar com o Miguel (o portal dele lê a tabela).
- **Tarefas de imóveis (852), entidades (478) e processos (70)**: sem `oportunidade_ref`, hoje também ficam de fora. Só se contam.
- **310 tarefas sem ligação** (leads arquivadas): `GetOpportunity` resolve ~229 para `VEN_`/`CAP_`/`LLO_` mas quase nenhuma existe em `oportunidades`
  e a FK impede a gravação. Ficam saltadas e contadas; a F3 (oportunidades pela API) é que as pode resolver.
- **Ramo de tarefas do relatório das oportunidades** (`sync-oportunidades`, 03:37): continua a gravar as tarefas das oportunidades editadas nas
  últimas 48 h, com a mesma chave. Mantém-se até à F3. A F2.0 verifica que os dois caminhos produzem linhas iguais (descrição, estado, datas),
  senão cada um sobrescreve o outro todos os dias.
- Sem escritas no eGO. Sem migration (nenhuma coluna nova).

## Prova
- `backend/tests/test_tarefas_api.py`: mapeamento (estado, data → chave `dd/mm/aaaa` de Lisboa, sem `oportunidade_ref`), paginação incompleta
  levanta, snapshot parcial não fecha, travão de fecho em massa, FK salta e conta, `fonte`/origem só `todas_as_colunas`. Sem rede.
- F2.0 e F2.2 `dry` em produção, só leitura, com contagens. Critério de passagem: pendentes API = relatório ±1%, a inserir ≈ 0 (chave igual).

## Decisões por tomar
1. Aprovar este âmbito: snapshot só de pendentes, outros estados saem por fecho (fecha a decisão 1 do plano-mãe).
2. Responsável e criado por: se a API só der ids, aceitas nomes por listagem de utilizadores, ou ficam como ids?
3. Limpeza das 3 397 pendentes legadas: com o Miguel, depois da F2.0.
4. Quando retirar o scraper de tarefas (F2.4): depois de quantos dias limpos.

## Risco
Leituras: baixo (46 páginas por snapshot, token de 24 h). Escrita na BD: o mesmo upsert de hoje, linha a linha, atrás de interruptor com
reversão imediata. O maior risco é a chave (duplicados por formato de data) e o fecho em massa: ambos cobertos pela F2.0 e pelos travões.
