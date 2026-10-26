# Oportunidades apagadas no eGO (plano, pedido #31 do Miguel)

> Estado 26/10: **implementado e em produção** (`973bc22`, `7fe10f9`; migration `0054` corrida). Corrida manual às 12:07 UTC marcou VEN_22261 e VEN_22277, sem erros. Falta só ver o cron das 04:17 a correr sozinho e a nota ao Miguel (#31 «Entregue»).
> - **Armadilha encontrada na 1.ª corrida:** o `GetOpportunity` dava 400 em produção porque o id ia no caminho (`?opportunityId=`) e o httpx 0.28 do Fly substitui a query pelo `params=` (o 0.27 local junta-os). `_pedido` passa a juntar `params=` ao `applicationId`; teste de regressão.
> - O resumo só regista `erros`; sem email se falhar a confirmação (avisar quando `erros` > 0 fica por fazer).

## Problema

Uma oportunidade apagada no eGO deixa de vir nos relatórios e o sync (que só lê as «editadas nas últimas 48 h») nunca a relê:
continua no Supabase como «Ativa» ou «Perdida» para sempre. Tem efeitos reais: `leads_para_ego._responsavel_da_oportunidade` trata-a
como uma oportunidade ativa e **não cria a lead** dessa pessoa, e entra nas contagens do painel. Casos de 25/10: VEN_22277 (teste do Miguel,
«Ativa», apagada a 19/10) e VEN_22261 («Perdida», apagada a 6/10).

## O que o eGO diz (medido a 26/10, só leitura)

- Apagada na aplicação é **lógica**: `GetOpportunity` continua a responder com `fieldStatusId = 1` (as ativas têm 0) e deixa de aparecer em
  `ListOpportunityByPage`. Pode também dar 404.
- **Arquivada ≠ apagada.** As arquivadas também não estão na lista ativa (`leadArchived: 0`, 2 688 linhas a 26/10), mas têm `archived = true`
  e `fieldStatusId = 0`. No Supabase 22 509 «Ativas» contra 2 688 ativas no eGO: quase todas arquivadas. Faltar na lista ativa **não** chega.
- Candidatas (editadas nos últimos 60 dias e fora da lista ativa): 2. Volume baixo.

## Desenho

1. **Migration `0054`:** `oportunidades.apagada_no_ego boolean not null default false` e `apagada_em timestamptz`. Aditiva. Notas, tarefas e
   histórico não se tocam.
2. **Passo diário** no mesmo cron das propostas (04:17 UTC, `POST /api/oportunidades/sync/propostas`; o resumo ganha a chave `apagadas`):
   - `ego_api.refs_ativas()`: uma chamada à `ListOpportunityByPage` (`leadArchived: 0`); levanta se a contagem não bater com o `totalRows`
     (nunca marcar com uma lista parcial).
   - Candidatas: `apagada_no_ego = false`, `ego_editado_em` nos últimos **90 dias**, referência fora da lista ativa. No máximo **100** por volta
     (as mais recentes primeiro); as restantes ficam para o dia seguinte e contam em `adiadas`.
   - Para cada uma, `GetOpportunity`: `fieldStatusId = 1` ou **404** → marca (`apagada_no_ego = true`, `apagada_em = agora`). Arquivada ou
     ativa → não marca. Um erro noutro código conta em `erros` e não marca.
   - **Desmarca** as marcadas que voltem à lista ativa (se o eGO a repôs).
   - Falha numa parte não esconde a outra: as propostas e as apagadas correm cada uma em `try`.
3. **Consumidor do nosso lado:** `_responsavel_da_oportunidade` ignora as apagadas (`apagada_no_ego = false`).
4. **Fora desta fase (decisão):** a função `dashboard_metricas` (migration `0015`) conta todas as linhas. Reescrevê-la a partir da cópia do
   repo arriscava reverter alterações feitas na interface do Supabase («o repo não é a fonte de verdade única»); com 2 linhas em 26 mil
   o efeito é desprezável. Fica para quando houver a definição viva (`pg_get_functiondef`). O **portal do Miguel** (listas e crons) é código
   dele: a nota diz que passou a haver `apagada_no_ego` para filtrar.

## Testes

Refs ativas (parcial levanta); candidata apagada marca; arquivada não marca; 404 marca; erro noutro código não marca; marcada que reaparece é
desmarcada; limite de 100 e `adiadas`; só candidatas editadas na janela; o endpoint corre as duas partes mesmo que uma falhe; a oportunidade
apagada já não bloqueia `_responsavel_da_oportunidade`.

## Passos (cada escrita em produção só com ordem expressa)

1. Migration `0054` (a correres tu).
2. Commit, push e deploy do `figueirahome-agentos` (o cron já existe; **sem a coluna, o passo falha e conta em `erros`**, por isso a ordem conta).
3. Verificar no dia seguinte: VEN_22277 e VEN_22261 marcadas.
4. Docs: CLAUDE.md e este plano.
