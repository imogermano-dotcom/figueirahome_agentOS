# Notas pela API do eGO (fase A2) — plano

> Fase A2 de `ego-api-substituir-scrapers-plano.md`. **Plano antes de código.** Tudo o que está medido foi lido a 31/10 só em leitura
> (nenhuma escrita). Nada de A2 está implementado.

## Porquê
O sync por relatório (janela de 48 h) grava as notas da oportunidade na mesma volta. Quando a oportunidade era recusada (o «Criada» de
21–30/10) as notas caíam em cascata (180 e 492 a 27 e 28/10, 93 e 63 a 29 e 30/10). As 55 oportunidades recuperadas pela API a 31/10
nasceram sem notas. A API dá as notas por lote de oportunidades, sem depender de edição nem de relatório.

## O pedido (`POST /note/Note/ListNotesByPage`)
- Corpo: `objectName: 3` (oportunidade), `objectIds` (ids da API, até 200 por lote), `pageIndex`, `numberOfRecords`, **e `applicationId` também
  no corpo** (só na query dá HTTP 400 «ApplicationId must be greater than 0»; é o buraco que se repete em várias listagens).
- Resposta: `{"items": [...], "totalCount": N}`. Cada nota: `id` (estável), `objectId`, `description` (HTML), `securityUserId`, `createDate`,
  `alterDate`, `historicTypeId`, `fileList`, `objectAssociatedId/Name`.
- `objectId` é o `id` da API da oportunidade (o mesmo de `oportunidades_ativas()`), **não** `oportunidades.id`. A ligação é por `name` = `oportunidade_ref`.

## Medido a 31/10 (as 2 793 oportunidades ativas, 14 lotes de 200)
| | |
|---|---|
| Notas na API | 13 820 |
| Notas na BD das mesmas oportunidades | 21 378 |
| Oportunidades com **menos** notas na BD do que na API | 438 (648 notas em falta) |
| Dessas, com **0** notas na BD | 121 |
| Oportunidades com **mais** notas na BD do que na API | 1 163 |

Notas em falta, por mês de criação da oportunidade: jul/2026 **266**, ago **213**, out **117**, set 22, jun 21, mais algumas de meses antigos.

Leitura, com cautela:
1. A BD tem **mais** notas do que a API nas ativas. Só comparei contagens, não o conteúdo: pode haver duplicados na BD (a chave atual é
   `(oportunidade_ref, nota_texto, nota_data_raw)`, texto repetido), notas de outros objetos, ou notas que a API não devolve com este filtro.
   **Por explicar antes de gravar.**
2. As notas em falta **não são só do «Criada»** (out = 117). Julho e agosto pesam mais (479): oportunidades criadas nesses meses cujas notas
   nunca chegaram à BD, provavelmente porque ninguém as editou na janela das 48 h depois de a nota ser escrita. É o mesmo defeito de fundo (a nota
   não conta como edição da oportunidade), por isso a API resolve-o e o relatório não.

## Passo 1 feito (31/10): comparação por nota, só leitura
Chave: `(oportunidade_ref, data da nota, primeiros 50 caracteres do texto sem HTML)`, nas 2 793 ativas.

| | API | BD |
|---|---|---|
| Notas | 13 820 | 21 378 |
| Chaves distintas | 13 600 | 14 389 |
| Duplicados (mesma chave repetida) | 220 | **6 989** |

- **Os 6 989 duplicados da BD explicam quase toda a diferença de contagem.** A mesma nota entra uma vez por cada lista de origem (`Ativas`, `Arquivadas`,
  `todas_as_colunas`) porque a chave de upsert inclui o texto e a data crua e não distingue a lista. Com a chave `id` da API isto acaba.
  **Não se apagam duplicados nesta fase** (apagar notas é decisão à parte, com o Miguel).
- **Só na API: 673 chaves.** 333 têm texto vazio depois de tirar o HTML (eventos e anexos, `historicTypeId` ≠ 0); as restantes ~340 são notas com texto.
  Por mês em que a nota foi escrita: jul **264**, ago **199**, set 67, out 138. Ou seja, o buraco não é só o «Criada» (out).
- **Só na BD: 1 462 chaves**, 1 315 vindas da lista antiga `Ativas`, 364 com origem `portal`. A API não as devolve com este filtro: podem ser notas apagadas
  no eGO, notas do portal (não são do eGO) ou texto que difere do HTML. **Por explicar; não se mexe.**

Consequência para o passo 2: gravar só as ~340 com texto (as 333 vazias não trazem informação) dispara ~340 chamadas de IA, não 648.

## Âmbito
**Passo 1 — comparar a sério (leitura):** por nota, não por contagem. Chave de comparação: `(oportunidade_ref, data da nota, início do texto sem HTML)`.
Explicar os 1 163 casos de a BD ter mais; confirmar que as 648 em falta são notas reais (não duplicados de formatação). Sem PII no relatório (contagens e referências).

**Passo 2 — gravar as em falta:**
- Só INSERT (nunca apaga nem edita notas existentes).
- **Cada INSERT em `notas` dispara IA** (`tgr_classify_lead`, `tgr_extract_prefs` → edge functions): gravar 648 notas dispara 648 chamadas. Dizer isto antes e
  decidir se se grava em lotes pequenos. `contacto_id` herda da oportunidade pela RPC `propagar_contacto_id`.
- Coluna `nota_ego_id` (migration à mão, explicada antes) para a chave passar a ser o `id` da nota e acabarem os duplicados por texto repetido.
  Sem a migration dá para gravar com a chave atual, mas fica com a fragilidade de sempre.

**Passo 3 — rotina diária:** passo no cron das 04:17 (`reconciliar_propostas`) que lê as notas das ativas por API e grava as novas. Só depois de o passo 2 estar estável.

## O que não faz
- Não desliga o scraper nem o relatório; não apaga notas; não toca nas arquivadas.
- Não faz `UpdateNote`/`InsertNote`: só leitura do eGO.

## Decisões por tomar
1. **Migration `nota_ego_id`** (corrida por ti): agora, ou gravar já com a chave atual?
2. **Disparo da IA** nos INSERT: aceitável gravar 648 notas de uma vez, ou em lotes?
3. As notas de **julho/agosto** valem a pena? São antigas; o benefício é o histórico completo da oportunidade.

## Testes
- Mapeamento `description` (HTML) → `nota_texto`; `createDate` → `nota_data_raw`/`nota_data_iso`; sem rede (`httpx.MockTransport`).
- Chave de comparação e dedupe, com os casos de texto repetido.

## Risco
Leitura: baixo. Escrita: INSERT linha a linha, reversível pelo registo em `agente_sync_log`. O risco real é o disparo da IA e os duplicados.

**Estado: plano escrito a 31/10; passo 1 feito (resultado acima); passo 2 por decidir.**
