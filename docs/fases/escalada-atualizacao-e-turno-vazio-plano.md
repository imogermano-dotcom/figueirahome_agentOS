# Atualização da escalada + turno vazio com resposta real — plano

> Mexe em `tools._escalar_para_humano`, `engine` (fallback do turno vazio e nota de estado).
> **Plano antes de código** (CLAUDE.md, regra 2). Continua `estado-da-conversa-e-aviso-unico-plano.md`.
> Origem: conversa de uma candidata da Inês a 13/10 (11:32–11:44, WhatsApp), analisada só em leitura.

## Problemas (medidos na conversa de 13/10)

### P-A. Turno vazio respondido com frase enlatada que não responde (11:41)
- A candidata disse "Eu não tenho carta de condução" (possível impedimento). Turno com 3 iterações,
  `erro='sem_texto'`, **1.ª chamada de `guardar_dados_cliente` da conversa** — logo não é repetição de tool e
  a nota de estado não se aplica. O modelo guardou os dados a meio da conversa e fechou sem texto.
- A frase neutra de 08/10 ("Fica registado. Se precisar de mais alguma coisa…") evitou o "Ocorreu um erro" mas não
  respondeu: a candidata teve de repetir a pergunta um minuto depois.
- Hoje o fallback (`engine`, "chamada final sem tools") reenvia **o mesmo histórico** com `tool_choice: none`; o histórico
  acaba num `tool_result` sem nenhuma instrução, e o modelo volta a calar-se.

### P-B. Informação nova depois de escalar perde-se (11:44)
- Tarefa de escalada às 11:44:21; a candidata escreve às 11:44:28 "Só dá para a semana". A Inês volta a chamar
  `escalar_para_humano` (com motivo legítimo: informação nova); o dedup (`_tarefa_ja_registada`) responde "Já está
  registado" e **descarta o resumo**. Verificado: "semana" não está na descrição da tarefa nem nas notas do cliente.
- A Inês diz à candidata "O responsável terá isso em conta" — promessa sem registo. O responsável liga sem saber.
- A nota de estado de 08/10 manda **não** voltar a chamar `escalar_para_humano`; hoje isso entra em conflito com o
  caso (legítimo) de haver informação nova.

## Proposta

### P1. Fallback do turno vazio: primeiro tenta responder a sério (`engine`)
Antes de cair na frase enlatada, a chamada final sem tools passa a levar uma instrução explícita no último turno do
utilizador (bloco de texto a seguir aos `tool_result`, que a API aceita): *"Escreve agora a resposta à última mensagem
da pessoa, em texto, sem usar tools."* Se o último turno for texto simples, converte-se em lista com o texto + a
instrução. Se mesmo assim vier vazio, **mantém-se** a frase enlatada como último recurso (`_sem_erro_apos_registo`,
sem mudança). `erro='sem_texto'` continua a gravar-se (medição).

### P2. Escalada repetida com informação nova atualiza a tarefa (`tools._escalar_para_humano`)
- Quando o motivo já está registado: em vez de devolver só "já registado", procura a tarefa pendente
  (`conversa_id` + `tipo='escalar'` + `motivo`) e, **se o `resumo` traz algo que a descrição ainda não contém**,
  acrescenta `\n\nAtualização às HH:MM (Lisboa): <resumo>` à `descricao`. Resumo vazio, igual ou já contido → não faz nada.
- Retorno ao modelo: "Atualizado: o responsável vê a nova informação. Confirma à pessoa." (ou o texto atual de
  "já registado" quando não há nada novo — mantém o dedup que impede tarefas duplicadas).
- Tarefa já `concluida`/`cancelada` (só se atualiza `pendente`): cai no comportamento de hoje.
- Limite de tamanho (`ponytail:` 4 000 caracteres na descrição; acima disso não acrescenta e regista aviso).
- **Email de atualização** (decisão 1): um email curto "Atualização — <motivo>" com o resumo novo, uma vez por
  atualização efetiva (nunca para repetições sem nada novo).

### P3. Nota de estado compatível com P2 (`engine._NOTA_ESCALADA`)
Troca o "não voltes a chamar escalar_para_humano para o mesmo motivo" por: "só voltas a chamar escalar_para_humano se a
pessoa der informação **nova** para o responsável (por exemplo disponibilidade ou outro contacto); nesse caso o resumo
tem só o que é novo." O resto da nota mantém-se (responder sempre em texto, frase curta a agradecimentos).

## Fora desta fase
- A resposta ao lado em "eu fui e não fiquei" (a Inês leu como preocupação com a carta): o facto chegou ao responsável
  no resumo; é um caso único, fica registado, sem alteração de prompt por agora.
- Sinalizar "ex-candidata/ex-colaboradora" como prioridade no painel.
- Persistir `tool_use` no histórico; nudge/horas de silêncio; backfill das leads dos assistentes.

## Testes (`backend/tests/`)
1. P1: payload da chamada final inclui a instrução no último turno (lista com `tool_result` + texto; e texto simples
   convertido); com resposta vazia mantém a frase enlatada; erro de rede mantém `erro` com `sem_texto;`.
2. P2 (Supabase falso com estado): 2.ª escalada com resumo novo → 1 tarefa, descrição com "Atualização às"; mesmo
   resumo outra vez → inalterada e sem email; resumo vazio → inalterada; tarefa `concluida` → comportamento de hoje;
   limite de tamanho; email só quando há informação nova.
3. P3: a nota já não proíbe a repetição por completo e contém "nova"; continua estável entre turnos (cache) e a
   regressão de 08/10 (uma só vez, ordem fixa) mantém-se verde.

## Medição depois do deploy
- `sem_texto` com frase enlatada (`erro='sem_texto'` e resposta = frase fixa) → deve baixar; contar quantos viram resposta real.
- Escaladas com `Atualização às` na descrição vs. turnos que repetem `escalar_para_humano` sem nada novo (não devem
  gerar email). Mesma consulta de 08/10/12/10 para repetições pós-escalada.

## Risco
- P1 acrescenta uma instrução só no turno de recuperação (raro); sem migration. P2 escreve em `agente_tarefas.descricao`
  (campo de texto livre que o painel já mostra). Reversível com `git revert`.
- Mais emails ao Miguel/consultoras se a decisão 1 for "sim": 1 por informação nova, não por repetição.

## Decisões (13/10)
1. ~~Email ao atualizar a tarefa~~ — **decidido: sim**, curto, só quando há informação nova.
2. ~~Acrescentar ou substituir~~ — **decidido: acrescentar** à descrição ("Atualização às HH:MM: …").
   Limite assumido: só deteta repetição **literal**; se o modelo reescrever o resumo todo, repete-se o conteúdo
   antigo na atualização (a nota pede "só o que é novo").
3. ~~Textos da instrução (P1) e da nota (P3)~~ — **aceites como propostos** (não houve objeção).

**Estado: implementado a 13/10 (346 testes), por deployar.**
