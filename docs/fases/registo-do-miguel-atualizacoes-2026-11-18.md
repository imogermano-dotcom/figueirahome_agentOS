# Registo do Miguel: estados e notas em falta (18/11/2026)

Texto para colar no artefacto «Registo para o developer». Sem nomes nem telefones de clientes.
Origem: registo exportado a 18/11 (#1 a #58, 58 linhas) comparado com o de 11/11 e com o trabalho feito desde 31/10 (`git log`).

**O que mudou no registo entre 11/11 e 18/11:** só #45 (1 nota nova) e #58 (texto do pedido e 2 notas). Nenhum ponto novo, nenhum estado alterado.
**O que ficou por registar:** os 8 pontos abaixo têm trabalho feito sem o estado ou a nota correspondente.

## A corrigir (por prioridade)

### #25 — Agente de voz: sem nota nenhuma desde 03/10
- **Estado:** Pendente → **Em curso** · **Com quem está:** Developer.
- **Nota (Developer):** A voz já atende em produção no +351 233 060 000 desde 19/10, e desde 26–27/10 como canal do mesmo motor das conversas de WhatsApp (mesmos assistentes, só ferramentas de registo, sem apresentação repetida). A frase sai logo e o registo corre a seguir (a 1.ª chamada real a 27/10 levou 6,9 s no turno com ferramenta; falta medir a melhoria). Ainda não está: pesquisa de imóveis por voz, interromper o agente a meio da frase e passar a chamada a um consultor. As vozes por agente (reunião de 28/10) ficam pendentes.
- **Já estava preparado:** o texto de 30/10 já propunha «Em curso», mas não chegou ao artefacto.

### #8 — Tarefas do eGO: sem nota desde 26/10 e o passo prometido está feito
- **Estado:** Pendente → **Em curso** · **Com quem está:** Developer.
- **Nota (Developer):** Feito a 17/11 o que propus a 26/10: as tarefas passam a vir da API do eGO (antes, de um relatório lido pelo navegador), ligado desde 17/11 e a correr sozinho no cron das 05:07 (18/11: 2 113 pendentes no eGO, 2 049 gravadas e ligadas à oportunidade, 0 fechadas). 33 ficam de fora por a oportunidade ainda não existir na base e 25 por não terem oportunidade (imóveis, entidades, processos). Também ficam corrigidas as descrições com pontuação perdida. Falta: guardar o id da tarefa no eGO (precisa de uma coluna nova, a pedir-te antes) e as 3 397 pendentes antigas que nenhum sync fecha, das quais 671 estão em oportunidades sem nenhuma tarefa pendente no eGO. Pergunta: queres que prepare a lista para veres com o consultor antes de eu fechar?

### #17 — Criar a lead no eGO: a nota de 11/11 diz mais do que estava feito
- **Estado:** mantém-se **Entregue** · **Nota (Developer):** Correção à nota de 11/11: o ponto 2 («se é de outro imóvel, cria-se a lead normalmente») só valia para a criação automática das 2 h. Quando a pessoa recusa o WhatsApp e já tinha oportunidade ativa de outro imóvel, a lead continuava a não ser criada. Corrigido a 13/11 (recusa e criação automática passam a ver o imóvel). Também a 12/11: uma lead já no eGO que volta a responder e fica qualificada gera um email à consultora e ao diretor («já no eGO voltou a responder»). A 02/11: «interessado» com negação («não estou interessado») deixou de contar como pedido de informação (uma lead criada a quem recusou a 01/11).

### #58 — Telefone da ficha antiga: faltam as notas do que se fez depois de 10/11
- **Estado:** Pendente, **Com quem está:** Developer (confirmar).
- **Nota (Developer):** Feito desde 09/11: o envio, os follow-ups e a criação no eGO usam o primeiro número válido; o RPC acrescenta o número do formulário à ficha sem apagar o antigo (migration 0059, aplicada); o scraper deixou de copiar uma lista de números para o telefone; a limpeza tratou 84 das 168 fichas com telefone inválido. Por fazer: a restrição na base de dados que recusa telefones com mais de 15 dígitos ou vários números (migration 0058, escrita, ainda não aplicada) e as 84 fichas restantes, que não se adivinham e precisam de ordem tua. **Etapa 5 (a Matilde não começa a conversa quando o contacto já existe no eGO):** as 5 leads foram criadas no eGO a 13/11.
- **Por confirmar contigo antes de colar:** se o 5a (porque o template não saiu nessas 5) e o 5b (garantir que o contacto existente recebe sempre a mensagem) foram investigados noutra sessão. Se não, ficam como estão, sem nota.

### #45 — Imóveis de todos os estados: falta a nota de 17/11
- **Estado:** mantém-se **Em curso** · **Com quem está:** Miguel.
- **Nota (Developer):** Dos 4 estados divergentes que ficaram à tua decisão, o FH2491 estava Disponível no Supabase e o sync não o atualizava por ter a marca de imóvel manual; passou a Retirado a 17/11, com o teu OK. Ficam FH2574, FH2552 e FH2483_B (este depende de resolveres os duplicados no eGO) e os 258 imóveis legados sem angariador.

### #49 — Insistir depois de uma recusa: afinações de 05 e 06/11 sem nota
- **Estado:** mantém-se **Entregue** · **Nota (Developer):** A deteção do fim de conversa foi alargada a 05 e 06/11 («boa noite», «abraço», «estou por aqui», «muitíssimo obrigado», «fico à disposição», «quando precisar», «bom dia/boa tarde»): a assistente já não responde a essas despedidas. A 10/11 quem pediu visita deixou de receber o «Ainda está interessado?» do follow-up. A cascata e a reativação continuam por existir.

### #20 — Notificação por email: os emails novos desde 26/10
- **Estado:** mantém-se **Em curso** · **Nota (Developer):** Desde 26/10 acrescentei: a tarefa da escalada passa a ter responsável (01/11); o email à consultora de uma lead já no eGO que volta a responder (12/11); e o aviso à consultora quando a lead nova se junta a uma oportunidade ou lead existente (13/11). Falta o resumo da conversa no email de lead qualificada.

### #9 — Cliente já existe: o aviso à consultora está feito; falta o resumo
- **Estado:** mantém-se **Pendente** · **Nota (Developer):** Desde 13/11, quando a lead nova coincide com uma oportunidade ou lead existente, a consultora é avisada por email. Continua por fazer o resumo do cliente (oportunidades, última interação, notas, consultor) e a regra dos 90 dias (#30).

## Opcional

### #28 — Notas
- **Nota (Developer):** As notas novas passam a poder vir da API do eGO no cron das 04:17 (31/10), ainda desligado: a 18/11 conta 0 por gravar e o relatório continua a ser a fonte.

## Não há nada a registar
- **#4, #27, #31, #34, #42, #43, #44, #48, #56, #57:** estado e notas coerentes com o trabalho feito.
- **#1, #5, #10–#12, #14–#16, #18, #21–#24, #26, #30, #35–#41, #46, #50–#55:** sem trabalho novo da nossa parte. O #41 (comissões) continua à espera do eGO.
