# Notas pela API com autor e tipo, para tirar as notas do relatório (pedido #28, 26/11)

**Plano antes de código; nada deste plano está implementado.** Sem textos de notas nem nomes de pessoas (só contagens e códigos).
Continuação de `notas-dedup-e-cadencia-plano.md` (feito a 26/11: dedup das notas do portal, endpoint e cron `sync-notas` de hora a hora).

## Objetivo
Parar de gravar notas a partir do relatório do scraper (um passo da A8 de `ego-api-substituir-scrapers-plano.md`), para que as notas tenham uma só fonte, a API, e deixem de nascer duplicados.

## Medido (26/11, só leitura)
- **O que uma nota da API traz:** `id`, `objectId` (a oportunidade), `securityUserId`, `createDate`, `alterDate`, `historicTypeId`, `fileList`, `description`. Não traz resultado nem cliente.
- **O que as notas gravadas pela API não têm hoje:** `nota_autor` (0 % das 17 linhas da API, 100 % do relatório e do portal), `nota_tipo` (0 %) e `nota_resultado` (0 %). O relatório preenche `nota_tipo` em 36 % e `nota_resultado` em 15 %.
- **Autor:** `securityUserId` + `ego_api.utilizadores()` (`ListEmployees`, já usado nas tarefas). Em 2 325 pares da mesma nota (API e relatório) o nome bate em **2 299 (98,9 %)**; 15 têm o utilizador fora do mapa (quem já saiu do eGO) e 11 têm um nome diferente (por ver porquê).
- **Tipo (`historicTypeId`):** `58` Tarefa concluída, `81` Ponto de Situação, `2` Sistema, `88` Criação de oportunidade, `4` Estado oportunidade, `65` Clique em Newsletter; `0` é a nota normal de texto (sem tipo no relatório). Vistos na API sem correspondência no relatório: `34`, `82` e um código isolado. A API tem **mais** tipo do que o relatório (o relatório deixa `nota_tipo` vazio em 256 das `58`).
- **Cobertura:** as 1 379 notas gravadas pelo relatório desde 15/10 são todas de oportunidades ativas; 96,5 % estão na API pela chave (ref, dia, texto); 48 não batem, 47 por a API ter uma nota do mesmo dia a começar por um ícone que o relatório não traz (por ver se são as mesmas).
- **Latência hoje:** 1 nota por oportunidade por volta (hora a hora). Notas de oportunidades criadas hoje (`sem_oportunidade`) esperam pelo relatório das 03:37, que ainda cria a oportunidade.

## Desenho

### 1. Gravar autor e tipo nas notas da API
Em `ego_notas`:
- `gravar` lê `ego_api.utilizadores()` uma vez por volta; `linha_de_nota` passa a incluir `nota_autor = nome` (se o `securityUserId` não está no mapa, fica vazio e conta em `autor_desconhecido` no resumo) e `nota_tipo` pelo mapa `_TIPOS = {58: "Tarefa concluída", 81: "Ponto de Situação", 2: "Sistema", 88: "Criação de oportunidade", 4: "Estado oportunidade", 65: "Clique em Newsletter"}` (código fora do mapa → vazio e conta `tipo_desconhecido`, para o mapa crescer com o uso).
- `notas_da_api`/`so_na_api` passam `securityUserId` e `historicTypeId` até à linha (hoje só passam `ego_id`, ref, dia e texto).
- Falha a ler os utilizadores não pára a volta: grava sem autor e regista.

### 2. Completar as linhas já gravadas pela API (17)
UPDATE só dos campos vazios (`nota_autor`, `nota_tipo`) nas linhas com `nota_ego_id` e `nota_origem='crm'`, por `id`, depois de ver a lista de ids. Só com OK.

### 3. Comparar antes de desligar
Script de leitura (`scripts/`), sem imprimir textos: para as notas que a API e o relatório têm, conta onde o autor e o tipo divergem. Critério para avançar: **autor e tipo iguais em ≥ 99 %** durante 5 dias úteis seguidos, e as divergências explicadas (as 11 de autor e as 48 que não batem), vendo só estrutura: código, dia, ícone inicial, comprimento.

### 4. `nota_resultado` (15 % no relatório)
A API não o dá. Pergunta ao Miguel: **alguém usa `nota_resultado`** (portal, resumo do cliente #9/#30)? Se não, perde-se sem custo; se sim, fica por resolver (a nota continua a vir do relatório para esse campo, ou só se completa por UPDATE).

### 5. Tirar as notas do relatório
Interruptor `RELATORIO_SEM_NOTAS` no scraper (vazio = grava como hoje; `1` = não grava as notas do lote, só as tarefas, oportunidades, contactos…). Reversível por `secrets unset`. As oportunidades continuam a vir do relatório, por isso uma nota de uma oportunidade nova entra na volta seguinte à das 03:37.
Antes de ligar: janela de notas da API a cobrir o que o relatório trazia (relatório = todas as notas das oportunidades editadas em 48 h, API = notas dos últimos 7 dias); correr `ego_api_notas.py --desde` com uma data mais antiga para ver que não falta nada.

## O que não muda
Só INSERT (e o UPDATE dos 17 do ponto 2) em `notas`; nada se apaga nem se escreve no eGO. A chave do relatório e a PK não se tocam. O dedup das notas do portal fica (as notas do portal continuam a chegar pelo `nota_ego_id`).

## Riscos
- **Autor errado** por homónimos ou nome mudado no eGO: por isso a comparação com o relatório antes de desligar.
- **Tipo novo** que não está no mapa: fica vazio e visível no resumo; não bloqueia.
- **Menos informação no dia 1** de uma oportunidade nova (nota espera pela oportunidade). Aceite; 7 notas hoje.
- **`nota_resultado` perdido** se for usado: decide-se com o Miguel antes do ponto 5.

## Prova
- Testes: `linha_de_nota` com autor/tipo do mapa; utilizador fora do mapa → vazio e contado; tipo fora do mapa → vazio e contado; falha em `utilizadores()` → grava sem autor.
- Script de comparação (ponto 3) com os números por dia.
- Depois do ponto 5: nenhuma nota nova com `origem_lista='todas_as_colunas'` sem `nota_ego_id`, e a contagem de notas por dia igual à da API.

## Passos (cada um com OK próprio)
1. Código e testes do ponto 1 (sem commit); commit, push e deploy do agentos.
2. UPDATE dos 17 (lista de ids ao utilizador).
3. Script de comparação e 5 dias de observação; explicar as 11 e as 48.
4. Pergunta ao Miguel sobre `nota_resultado`.
5. Interruptor `RELATORIO_SEM_NOTAS` e desligar; nota no registo e CLAUDE.md.
