# Plano — sincronização completa das tarefas activas do eGO (29/09)

## Problema
`scraper/tarefas.py` descarregava o relatório "tarefas todas", mas (a) o eGO só dá
download directo até ~1000 linhas e (b) "criadas nos últimos 3 dias" nunca vê uma
tarefa antiga que foi concluída — o estado ficava "Em Curso" para sempre.

## O que se mediu (ao vivo, 29/09)
- `/egocore/tasks` lista por omissão só as **Activas: 2190** (2014 atrasadas).
  Concluídas: 13 732.
- Não há filtro de "editada em" nem de "concluída em". Há `filter_active`,
  `filter_complete`, `min/max_create_date`, `date_min/date_max` (agendamento).
- Acima de ~1000 o eGO manda o relatório por email ("vai demorar… foi agendado o
  envio para o seu email").

## Desenho
1. **Snapshot das activas em fatias** por data de criação, partidas ao meio até
   cada fatia ter ≤ 900 (contagem barata via `POST /egocore/search/eventsearch`,
   título "N Tarefas"). Verifica-se que a soma das fatias = total das activas.
2. Por fatia: pesquisa avançada da página (`filter_active`, sem "Minhas",
   intervalo de criação, `Search.byAdvanced`) → seleccionar todos → Relatórios →
   "tarefas todas" (mesmo `_trigger_and_download`, com `preparar` por fatia).
3. **Upsert** em `tarefas` (chave `oportunidade_ref + tarefa_titulo + tarefa_due_raw`).
4. **Fechar as desaparecidas**: linhas 
   `tarefa_status=pendente` (`origem_lista` = `todas_as_colunas`, o único valor do enum que é nosso) que já não estão no snapshot passam a
   `concluida`. Só corre com o snapshot completo; qualquer falha
   aborta antes de escrever.

## Formato do relatório (descoberto no ensaio)
1 linha base por tarefa (sem `Referência`) **mais** 1 linha extra por cada
oportunidade associada (com `Referência`): 5 tarefas, 4 com oportunidade = 9
linhas. A completude de cada fatia confere-se pelas linhas **sem** `Referência`
(= nº de tarefas da lista); só as linhas com `Referência` vão para a BD.

## Limites conhecidos
- Tarefa **apagada** no eGO também fica "Concluída (inferido)".
- Tarefa **reagendada** muda `tarefa_due_raw` (parte da chave): a linha antiga
  fecha, nasce outra.
- Tarefas sem `Referência` ou com referência ausente de `oportunidades` (FK) são saltadas: 2192 activas → 2125 gravadas (01/10).
- Cron: `sync-tarefas`, `7 5 * * *` UTC (Cron Manager, job 6) → `POST /api/oportunidades/sync/tarefas` (backend, `X-Sync-Secret`) → `POST /run/tarefas` (scraper). 05:07 UTC = 06:07 Lisboa no verão, 05:07 no inverno; fica 70 min antes do `sync-imoveis` (06:17) para não partilhar sessão eGO. Teste manual 01/10: ~135 s, `origem=cron`, idempotente.

## Resultado da 1.ª execução (01/10)
+363 inseridas, 1762 actualizadas, 321 fechadas (`pendente`→`concluida`); `Ativas`/`Arquivadas` intactas.
Erros apanhados no ensaio `--dry`: `origem_lista` é enum; a tabela não tem `tarefa_reagendamento_raw`; FK `tarefas_oportunidade_ref_fkey`.

## Verificação
`python tarefas.py` (auto-teste do mapping, da partição em fatias e da lógica de
fecho) · `python tarefas.py sync --dry` (descarrega, não escreve) ·
`python tarefas.py sync` (escreve).
