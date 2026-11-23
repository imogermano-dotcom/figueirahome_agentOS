# Fechar as tarefas pendentes antigas do eGO (pedido #8, 23/11)

## Problema
`tarefas` tem 5 449 pendentes. 2 052 vêm do sync pela API (`origem_lista='todas_as_colunas'`, com `ego_id`) e batem com o eGO.
As outras **3 397 são legadas** (`Ativas` 2 167 + `Arquivadas` 1 230, todas com `oportunidade_ref`, nenhuma com `ego_id`): nenhum sync
as toca, ficam `pendente` para sempre e inflacionam o portal do Miguel, as contagens e qualquer resumo de pendentes. O snapshot da
API é completo (as pendentes do eGO), logo uma legada que não corresponde a nenhuma pendente da API **já não está pendente no eGO**.
O Miguel disse que sim a fechá-las; falta o critério e a prova.

## Critério (por camadas, só leitura primeiro)
Comparar cada legada com o snapshot da API (`ego_api.tarefas_pendentes()`):
- **A. Oportunidade sem nenhuma pendente na API** (671 a 18/11): a oportunidade já não tem tarefas abertas, as legadas estão feitas → fechar.
- **B. A mesma tarefa já existe viva**: chave `(oportunidade_ref, título, data)` igual a uma linha `todas_as_colunas` pendente → a legada é cópia velha → fechar.
- **C. Resto** (≈ 2 700 a 18/11): oportunidade tem pendentes na API mas esta não aparece. Provável feita/reagendada/apagada, mas **não se fecha à primeira**: lista por contagens (por ano, tipo, consultor), amostra para o Miguel/consultores confirmarem.

Nunca fecha: linhas de outras origens, linhas com `ego_id`, nada se o snapshot vier incompleto (menos que o `totalRows`).

## O que não muda
Não toca no eGO. Só muda `tarefa_status` de `pendente` para `concluida` em `tarefas` (como já faz o sync). Nada se apaga.
O portal do Miguel lê esta tabela: as contagens de pendentes descem (é o pretendido).

## Reversão
Antes de escrever, guardar a lista de ids fechados (só ids, ficheiro fora do repo). Reverter = `update tarefas set tarefa_status='pendente' where id in (…)`.

## Passos (cada um com OK próprio)
1. **Dry-run em leitura:** script `scripts/fechar_tarefas_legadas.py` (`--aplicar` explícito, dry por omissão, sem nomes nem telefones na saída), com teste da classificação A/B/C sobre dados simulados. Saída: contagens A/B/C e C por ano/tipo.
2. **Rever as contagens contigo** e decidir o que fazer ao C (fechar também, fechar só as mais antigas que X, ou deixar).
3. **Aplicar A e B** (`--aplicar`, ids guardados), confirmar contagem de pendentes = 2 052 + C e que o cron de 05:07 UTC do dia seguinte não reabre nada.
4. **Decidir o C** com o Miguel; aplicar se for o caso. Depois: nota ao Miguel para fechar o #8 e atualizar o CLAUDE.md (linha «3 397 que nenhum sync fecha»).

## Riscos
- Chave com diferenças de texto/data entre legada e viva (a API corrige pontuação que o relatório perdia): por isso B é só para o que bate exatamente e o resto cai no C, nunca fecha por aproximação.
- Tarefa reagendada: muda a chave e a velha cai em B/C; está certo, a viva é a nova.

## Estado (23/11)
Passo 1 e 3 feitos para a camada **A**: dry-run A 674 / B 0 / C 2 723 (2 383 do C com o mesmo título vivo); fechadas as 674 (`Ativas` 653, `Arquivadas` 21);
pendentes 5 449 → 4 775 (2 052 da API + 1 514 `Ativas` + 1 209 `Arquivadas`). Decisão do utilizador: só A. **C por decidir** (com o Miguel); ids em ficheiro fora do repo.
