# Notas do eGO: sem duplicados do portal e entrada mais depressa (pedido #28 reaberto, 26/11)

**Plano antes de código; nada deste plano está implementado.** Sem textos de notas nem nomes de pessoas (só contagens).

## Pedido
Etapa de 23/11 do Miguel (#28): (1) importação das notas pela API, (2) backfill desde 21/11, (3) reconhecer as notas que o portal copia para o eGO (`InsertNote`, `notas.nota_ego_id`, texto a acabar em «— registado no portal Figueira Home por …») para não as duplicar. (4) o portal lê entretanto as notas recentes numa tabela à parte (`ego_notas_api`) e desliga-a quando a nossa importação estiver a funcionar.

## Medido (26/11, só leitura)
- **Buraco real, já fechado:** a 22/11 o relatório leu 168 notas e gravou 0 novas; a 23/11 o sync nem leu o relatório («0 oportunidades editadas nas últimas 48 h, confirmado pela API»). Voltou a gravar a 24/11 às 03:38. Escrever uma nota provavelmente não conta como edição da oportunidade (como as propostas).
- **Backfill:** `ego_api_notas.py --desde 2026-11-15` deu 1 nota por gravar de manhã e 32 ao fim do dia (todas de 26/11, notas novas das consultoras). Nada de 21–25/11 falta.
- **Rotina pela API** ligada a 24/11, 1.º ciclo a 25/11 04:17: `gravadas 0`, `por_gravar 0`, `erros 0` (o relatório já trazia tudo).
- **Duplicados do portal:** desde 23/11 há 58 linhas do portal (com `nota_ego_id`) e 42 cópias vindas do eGO com o sufixo e sem `nota_ego_id`; **4 repetem uma linha do portal**. A causa é o relatório: o scraper grava com a chave `(oportunidade_ref, nota_texto, nota_data_raw)`; o texto do portal não tem o sufixo, o do eGO tem, logo não há conflito e entra uma 2.ª linha. A via da API já reconhece o `nota_ego_id`.
- **Notas do relatório vs API:** 1 379 gravadas pelo relatório desde 15/10, todas em oportunidades ativas; 1 331 (96,5 %) estão na API com o mesmo dia e texto; 48 não batem pela chave (47 com uma nota do mesmo dia e oportunidade na API a começar por um ícone que o relatório não traz). Por ver se são as mesmas notas.
- **Latência:** a rotina grava **1 nota por oportunidade por volta** (uma volta por dia, 04:17) para os gatilhos de IA (`tgr_classify_lead`, `tgr_extract_prefs`) não correrem em paralelo para a mesma oportunidade. Hoje: 32 notas por gravar em 13 oportunidades; só 13 entram amanhã.

## O que o scraper é (corrige o «deixou de ser usado»)
O scraper continua a correr todas as noites (03:37 UTC) e é a fonte das oportunidades, contactos, visitas e preferências; só as tarefas e parte das notas vêm da API. Desligá-lo é a A8 do `ego-api-substituir-scrapers-plano.md` (A4 visitas e A6 contactos por começar; um mês de estabilidade). Retirar só as notas do relatório não se faz já: ver «Mais tarde».

## Desenho

### 1. Dedup das notas do portal no scraper (`scraper/upsert.py`)
Antes de gravar o lote de `notas`, para as notas cujo texto termina no sufixo do portal («— registado no portal Figueira Home por …»): ler de `notas` as linhas das mesmas `oportunidade_ref` **com `nota_ego_id`**, e **saltar** a nota se já existe uma com o mesmo dia e o mesmo início de texto (40 primeiros caracteres, sem espaços a mais, minúsculas). Conta `saltadas_portal` no resumo. Falha na procura → grava como hoje (nunca perde notas), regista `erros_procura_notas`.
Interruptor `DEDUP_NOTAS_PORTAL` (vazio = só conta `saltaria_portal`; `1` = salta), ligado em dois tempos como o #27.

### 2. Notas mais vezes por dia
- **Novo endpoint** `POST /api/oportunidades/sync/notas` (segredo de sync, como as propostas) que corre só `reconciliar_notas`. O passo diário das propostas **continua** a chamá-la (decidido ao escrever o código: tirá-la obrigava a reescrever testes sem ganho; às 04:17 grava 1 nota por oportunidade e a hora a hora grava as outras).
- **Novo cron** `sync-notas` (`crons/schedules.json`): `7 7-19 * * *` (de hora a hora das 07:07 às 19:07 UTC, todos os dias). Continua 1 nota por oportunidade e por volta, por isso 3 notas da mesma oportunidade entram em 3 horas, não em 3 dias, sem mexer nos gatilhos nem no Miguel.
- O log `egorealestate_notas_api` (`gravar`) e o resumo do endpoint (`egorealestate_notas`) dizem `gravadas`, `adiadas`, `erros` por volta. Falha do cron → `falha_de_sync` como nos outros.
- **Antes de ligar:** medir na app (512 MB, auto-stop) o tempo e a memória de uma volta (ler as notas de ~2 640 oportunidades); nas medições locais demorou cerca de 1 minuto e deu 2 timeouts em 4 tentativas. Se pesar, a volta lê só as oportunidades editadas ou com nota recente (janela de 7 dias) em vez de todas as ativas.

### 3. Limpar os duplicados já criados (4)
Lista só de ids (sem texto), mostrada ao utilizador. Apagar linhas nossas de `public.notas` com `nota_ego_id` nulo e sufixo do portal que repetem uma linha do portal: **só com OK expresso** e depois da correção 1, para não voltarem. Nunca se apaga nada no eGO.

## O que não muda
Só INSERT em `notas` pela API (nunca apaga nem edita); sem `InsertNote`/`UpdateNote`; arquivadas e notas anteriores a 7 dias de fora; o relatório continua a trazer notas até a A8. A chave do relatório não se altera (o pipeline do Miguel e a PK dependem dela).

## Riscos
- **Saltar uma nota que não era duplicada:** o início de texto igual no mesmo dia e oportunidade com `nota_ego_id`; na dúvida (texto diferente) grava. O modo de contagem mostra quantas saltaria antes de ligar.
- **Carga da hora a hora:** 13 voltas por dia; cada uma lê a API do eGO e o Supabase. Medir antes; o cron `sync-notas` fica `enabled: false` até ver a medição.
- **As 48 que não batem** podem vir a duplicar quando as notas do relatório saírem: ver abaixo.

## Mais tarde (não nesta etapa)
- Tirar as notas do relatório (adiantaria a A8): só depois de ver as 48 (estrutura, sem ler textos de clientes: mesmo dia/ícone inicial) e de a cadência da API chegar a «mesmo dia».
- `force` por oportunidade (reprocessar as preferências no fim): depende do URL e da autenticação da função do Miguel, que não estão no repo.

## Para o Miguel (nota do #28)
Importação pela API ligada desde 24/11, escreve em `public.notas` com as mesmas colunas e chave `nota_ego_id`; backfill coberto; o relatório (o scraper corre todas as noites, não saiu) deixou 4 duplicados das notas do portal, que se corrigem; a cadência da API passa a de hora a hora; **só desligar o `ego_notas_api` quando a hora a hora estiver estável** e o relatório deixar de trazer notas.

## Prova
- Auto-testes em `upsert.py`: nota com sufixo e linha do portal igual → salta; texto diferente → grava; falha na procura → grava; interruptor desligado → só conta.
- Teste de `reconciliar_notas`/endpoint: sem o passo das notas no endpoint das propostas; endpoint novo chama só as notas.
- Observação: `saltaria_portal` do 1.º ciclo antes de ligar; depois 0 duplicados novos (consulta de grupos `(ref, texto)` com `nota_ego_id`).

## Passos (cada um com OK próprio)
1. Código e auto-testes do dedup (modo contagem) e do endpoint/cron, sem commit.
2. Commit, push; deploy do scraper (de `scraper/`) e do agentos (de `backend/`).
3. Medir uma volta na app; ligar o cron `sync-notas` (`enabled: true`, deploy dos crons).
4. Ver a 1.ª corrida do scraper com a contagem; ligar `DEDUP_NOTAS_PORTAL=1` (`secrets deploy`).
5. Lista dos 4 duplicados ao utilizador; apagar só com OK.
6. Nota no registo (#28), CLAUDE.md e resposta ao Miguel.
