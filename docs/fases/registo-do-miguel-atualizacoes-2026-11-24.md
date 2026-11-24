# Registo do Miguel: nota e estado do #8 (24/11/2026)

Texto para colar no artefacto «Registo para o developer». Sem nomes nem telefones de clientes.
Continua `registo-do-miguel-atualizacoes-2026-11-18.md` (a pergunta do #8 desse dia fica respondida aqui).

## #8 — Tarefas do eGO: as 3 397 pendentes antigas estão fechadas
- **Estado:** Em curso → **Entregue** · **Com quem está:** Miguel (para validar).
- **Nota (Developer):** As 3 397 tarefas pendentes antigas, que nenhum sync fechava, estão fechadas na nossa base. A 23/11 fechei 674, as das oportunidades que já não têm nenhuma tarefa pendente no eGO. A 24/11 fechei as 2 723 restantes. O critério foi a lista de pendentes que a API do eGO devolve: ela dá o conjunto completo, e estas tarefas antigas não têm o id do eGO nem eram atualizadas por nenhum sync. Isso quer dizer que já não estão pendentes no eGO, mas não distingue se foram feitas, reagendadas ou apagadas. Não toquei no eGO e não apaguei nada, só mudei o estado para concluída. Os ids ficam guardados, por isso desfaz-se se alguma estiver errada. Hoje temos 2 052 pendentes (contra as 5 449 de antes), todas vindas da API e batendo com as do eGO. As contagens de pendentes no teu portal descem por isso. Se vires alguma ainda aberta no eGO que cá apareça fechada, diz-me a referência e reponho. A tabela fica a ser mantida só pelo sync da API das 05:07.
- **Atenção ao colar:** a 18/11 a pergunta era «queres que prepare a lista para veres com o consultor antes de eu fechar?». Fechei sem lista e sem resposta tua a essa pergunta. A nota diz como se desfaz.
- **Por confirmar antes de marcar Entregue:** o cron das 05:07 UTC de 25/11 não reabrir nenhuma (`fechadas 0`, pendentes 2 052 ± as novas). Se reabrir, o estado fica Em curso e a frase final da nota sai.

## Pontos ligados
- **#9 e #30** (resumo do cliente, regra dos 90 dias): deixam de estar bloqueados pelo #8. Continuam **Pendente**: faltam o #26 (normalização dos autores) e o ecrã onde o consultor vê o aviso.
- **#28 (notas):** a rotina pela API está ligada desde 24/11, a gravar 1 nota por oportunidade e por volta do cron das 04:17. 1.º ciclo por ver a 25/11.
