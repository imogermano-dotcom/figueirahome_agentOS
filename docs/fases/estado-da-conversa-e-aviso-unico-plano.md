# Nota de estado generalizada + um aviso por pessoa — plano

> Mexe em `engine.py`, `guards.py` (caminho de escrita de todos os canais). **Plano antes de código**
> (CLAUDE.md, regra 2). Continua `nota-de-estado-escalada-plano.md` (deployada a 08/10): aquela só cobria
> `escalar_para_humano`. Origem: conversa de teste no chat do site (08/10, Maria, `a2_geral`).

## Problema 1 — o turno vazio não é só da escalada

Conversa de teste do site, 08/10 17:06–17:08: depois de "Dados guardados com sucesso", a mensagem
"é tudo" fez o modelo **repetir `guardar_dados_cliente`** e fechar sem texto (`erro='sem_texto'`, 3
iterações) → a pessoa viu "Ocorreu um erro. Tenta novamente." Não houve `escalar_para_humano`, por isso nem a
frase neutra nem a nota de estado de 08/10 (ambas só para escaladas) entraram.

**Causa (a mesma):** o `tool_use`/`tool_result` não fica no histórico (`claude_messages` leva só `role` e
`content`); no turno seguinte o modelo não sabe que a tool já correu. **Medido** (nota de estado, 08/10):
74% dos turnos a seguir a uma escalada repetem as tools, 12 s de mediana contra 2 s.

### P1. Saber o que já correu, a partir do que já gravamos
`agente_interacoes.tools_usadas` guarda, a cada turno, as tools chamadas. Novo helper
`guards.tools_ja_usadas(conversa_id) -> list[str]` (nomes distintos e **ordenados**, falha aberta → `[]`),
restrito às tools de **registo** — `guardar_dados_cliente`, `escalar_para_humano`, `pedir_visita`,
`encerrar_lead`. **Não** inclui `pesquisar_imoveis`/`ficha_imovel`/`link_imovel`: repetir a pesquisa é normal.

### P2. Nota de estado por tool, no system prompt
Substitui a nota única de escalada por uma linha por tool já usada (texto fixo, ordem fixa → cache estável):
- `escalar_para_humano`: como hoje (com os motivos, de `agente_tarefas`; mantém-se `motivos_escalados`).
- `guardar_dados_cliente`: "Já guardaste os dados desta pessoa. Só voltas a chamar `guardar_dados_cliente`
  se ela der dados novos ou corrigir algum."
- `pedir_visita` / `encerrar_lead`: "já registado; não repitas."
Continua suave: as tools ficam disponíveis (a pessoa pode corrigir o orçamento a meio, como no teste:
"corrigo 350").

### P3. Fallback do turno vazio generalizado
`_sem_erro_apos_escalar` → `_sem_erro_apos_registo(resposta, tools_usadas, ja_usadas, escalados)`:
- escalada (neste turno ou antes): a frase de hoje ("…o responsável entra em contacto consigo…");
- só `guardar_dados_cliente`/`pedir_visita`: "Fica registado. Se precisar de mais alguma coisa, é só escrever."
  — sem prometer contacto de ninguém, porque aí ninguém foi chamado.
- sem nenhuma tool de registo: mantém o erro (turno vazio sem causa conhecida deve ver-se, não esconder-se).

## Problema 2 — três avisos para a mesma pessoa

Mesmo teste: **3 tarefas "Lead qualificada" e 3 emails** (Resend: `delivered`) em 29 s, ao diretor
comercial (e às consultoras dos imóveis das 2 leads da Meta).

### Como aconteceu (confirmado no código e nas horas das leads)
O telefone tinha **3 leads abertas** do mesmo cliente (2 da Meta de teste + 1 de assistente, de 21/09).
`_promover_lead` promove **uma lead por chamada** (`.limit(1)`) e cada promoção cria tarefa + email:
1. `find_or_create_cliente` → promove a Meta nº 1;
2. `promover_lead_do_cliente` (chamada nova de 08/10, logo a seguir) → promove a Meta nº 2;
3. o modelo repete a tool no turno seguinte → promove a lead de assistente (por `cliente_id`).
O cliente e o `contactos` **foram reutilizados** (1 e 1); a duplicação está só em `leads`.

### Medido (só leitura, 08/10): 9 de 294 telefones com lead aberta têm **2 leads abertas — todas Meta+Meta**
(a mesma pessoa a preencher o formulário duas vezes). Não são testes. Logo acontece em dados reais, ~3%.

### P4. Um aviso por pessoa (`guards._promover_lead`)
- Continua a promover a lead (estado `qualificada` + `qualificada_em`) — cada lead é um registo próprio.
- **Antes de criar a tarefa e o email**: se já existe uma tarefa com o mesmo título
  (`"Lead qualificada — passar ao eGO — <nome ou telefone>"`) criada nas últimas 24 h, **não cria tarefa nem
  email**; regista `logger.info("... aviso já enviado")`.
- Falha aberta no sentido seguro para o corretor: se a consulta falhar, cria a tarefa e envia (um email a mais
  custa menos do que uma lead sem aviso).
- Ceiling assumido (`ponytail:`): a chave é o título (nome ou telefone). Duas pessoas distintas com o mesmo nome
  e sem telefone, na mesma janela, partilhariam o aviso; improvável e visível no painel. Alternativa se
  aparecer: chave por `cliente_id` numa coluna nova em `agente_tarefas` (migration).

## Fora desta fase
- **Impedir a 2.ª lead no n8n/RPCs `lead_meta_*`** (reutilizar a lead aberta do mesmo telefone em vez de criar
  outra): é outra decisão, no n8n e no SQL. Não li as RPCs; antes de decidir, ler e medir o que fazem hoje.
- Fusão de duplicados em `contactos`, backfill das leads dos assistentes, nudge/horas de silêncio.
- Router: comprador no site que fica com a Maria (ver abaixo, decisão 3).
- Persistir `tool_use` no histórico (mudança grande no modelo de dados da conversa).

## Testes (`backend/tests/`)
1. `tools_ja_usadas`: nomes distintos e ordenados; ignora tools de pesquisa; sem conversa → `[]`; erro → `[]`.
2. `_montar_system_prompt`: sem estado igual a hoje; com `guardar_dados_cliente` a nota aparece uma vez; dois
   turnos iguais dão o **mesmo texto**; com escalada + guardar, ordem fixa.
3. Fallback: escalada → frase da escalada; só guardar → frase sem promessa; nenhuma tool → erro mantido.
4. `_promover_lead` (Supabase falso com estado): 2 leads abertas do mesmo telefone → 2 promovidas, **1 tarefa,
   1 `notificar`**; a 2.ª chamada dentro das 24 h não repete; passadas 24 h cria de novo; erro na consulta →
   cria e notifica.
5. Regressão: lead única continua a dar 1 tarefa e 1 email (teste de 08/10 mantém-se verde).

## Medição depois do deploy (mesma consulta de 08/10)
- Repetições de `escalar_para_humano` e de `guardar_dados_cliente` nos turnos seguintes: de 74% para <15%.
- `sem_texto` visíveis ao cliente: 0. "Servido de cache" sem cair.
- Emails de "Lead qualificada": no máximo 1 por pessoa por 24 h (contar no Resend/`agente_tarefas`).

## Risco
- Texto extra no prompt só em conversas com tools de registo usadas; sem migration; reversível com `git revert`.
- Cache: o texto muda quando o conjunto de tools usadas muda (1 miss por mudança, poucas por conversa).
- P4 suprime avisos a que a pessoa teria direito se as 2 leads fossem de **imóveis diferentes** (a consultora do
  2.º imóvel não seria avisada): ver decisão 2.

## Decisões (08/10)
1. ~~Frase do fallback sem escalada~~ — **decidido: serve** ("Fica registado. Se precisar de mais alguma coisa, é só escrever.").
2. ~~Aviso por pessoa ou por pessoa + imóvel~~ — **decidido: um aviso por pessoa** (P4 como proposto, sem `imovel_ref`).
3. ~~Router do comprador do site~~ — **decidido: não alargar o regex.** "terra", "garagem" e "quinta" servem tanto a
   quem compra como a quem vende, e um regex que acerta nuns erra noutros (a Bárbara é sentido único A2→A4).
   Fica para o encaminhamento pelo modelo, só se o `monitorizar_encaminhamento.py` mostrar `POR RESOLVER` > 0.
4. ~~Janela do aviso único~~ — **decidido: 24 h** por agora.

**Estado: plano fechado a 08/10. Por implementar** (P1–P4 com testes).
