# Nota de estado depois de escalar — plano

> Mexe em `engine.py` (caminho de todos os canais). **Plano antes de código** (CLAUDE.md, regra 2).
> Origem: conversa de uma candidata da Inês a 08/10 que recebeu "Ocorreu um erro. Tenta novamente."
> Já em produção como rede de segurança: `engine._sem_erro_apos_escalar` (frase neutra). Este plano
> ataca a causa.

## Problema (medido a 08/10, só leitura, `agente_tarefas` × `agente_interacoes` desde 01/09)

27 conversas escaladas (`tipo='escalar'`), 43 turnos depois do turno que escalou:

| | Valor |
|---|---|
| Turnos que repetem `escalar_para_humano` | **32 de 43 (74%)** |
| Turnos que repetem `guardar_dados_cliente` | 31 de 43 |
| Latência mediana desses turnos | **12,2 s** (contra 2,3 s sem repetição) |
| Turnos que acabaram sem texto (`erro='sem_texto'`) | 3 (7%) — a candidata via o erro |
| Por agente | Inês 30 de 41, Maria 2 de 2 |

Quase tudo é a Inês: é a que mais conversa depois de escalar ("Agora", "Obrigado", "Boa tarde"…).

### Causa

1. **O `tool_use`/`tool_result` não fica no histórico** (`claude_messages` leva só `role` e `content`).
   No turno seguinte o modelo vê "o responsável entra em contacto consigo", mas não vê que a tool correu.
2. **O prompt já proíbe** (Inês, ponto 7: "NUNCA voltes a chamar…") e **não chega**: 74% repetem.
3. **O dedup em código protege os dados, não a resposta** (`_tarefa_ja_registada` → "Já está registado"):
   1 tarefa só, mas dois pedidos à API de 12 s à toa, e às vezes o modelo, sem nada a dizer depois do
   `tool_result`, fecha com `end_turn` vazio (o fallback sem tools também falha).

## Proposta

**Dizer ao modelo o que ele não consegue ver**, calculado em código a partir da base (não pelo modelo):

### P1. Helper partilhado `guards.motivos_escalados(conversa_id) -> list[str]`
- `agente_tarefas` com `tipo='escalar'` e esse `conversa_id`; devolve os `motivo` distintos, **ordenados**
  (texto estável → a cache do prompt não parte a cada turno).
- **Falha aberta** aqui: sem saber, não há nota e o comportamento é o de hoje. (O nudge, `_conversas_escaladas`,
  falha fechada porque o erro dele é enviar; o erro deste é só voltar ao estado actual.)
- `nudge._conversas_escaladas` fica como está (batch, outra forma).

### P2. Nota no system prompt (`engine._montar_system_prompt`, novo argumento `escalados`)
Só quando a lista não é vazia, no fim do prompt, texto fixo + motivos:

> Estado desta conversa: o caso já foi entregue a um humano (motivo: «…»). Isso já está registado e
> o responsável vai contactar a pessoa. Não voltes a chamar `escalar_para_humano` para o mesmo motivo
> nem `guardar_dados_cliente` sem dados novos. Responde sempre em texto ao que a pessoa escrever
> (mesmo um agradecimento: uma frase curta). Só chamas tools se surgir um assunto novo.

- `conversa_id` é `None` no 1.º turno: sem nota, correcto (ainda não escalou).
- **Cache**: o system é um bloco com `cache_control`. A nota acrescenta texto fixo por conversa escalada:
  1 miss (escrita da cache) no 1.º turno depois de escalar, hits nos seguintes. Medir "Servido de cache"
  depois (aviso do CLAUDE.md: a zero havendo turnos multiplica o custo por 10).

### P3. NÃO retirar as tools
Alternativa rejeitada (retirar `escalar_para_humano`/`guardar_dados_cliente` nos turnos pós-escalada):
- A Maria pode escalar **vários motivos** na mesma conversa (2 de 27 conversas têm >1 motivo; o dedup é por
  motivo) e a pessoa pode dar dados novos depois de escalar. Sem tools, perdia-se esse caso em silêncio.
- Mudar o bloco `tools` também parte a cache de forma mais ampla que uma linha no system.
A nota é suave de propósito: «assunto novo» continua a poder chamar as tools.

### P4. Manter `_sem_erro_apos_escalar`
Rede de segurança já em produção; passa a cobrir também conversas escaladas **em turnos anteriores**
(hoje só cobre a tool chamada no próprio turno): o fallback usa `motivos_escalados` se `tools_usadas` estiver vazio.

## Fora desta fase
- Nudge/quiet hours, fusão de contactos, backfill das leads.
- Persistir `tool_use` no histórico (mudança de modelo de dados da conversa; maior e arriscada).
- Mesmo mecanismo para `encerrar_lead` / `pedir_visita` repetidos (medir primeiro; ver `_tarefa_ja_registada`).

## Testes (`backend/tests/`)
1. `motivos_escalados`: devolve motivos distintos e ordenados; `None`/sem tarefas → `[]`; erro da base → `[]`.
2. `_montar_system_prompt`: sem `escalados` o texto é igual ao de hoje (regressão); com `escalados` a nota
   aparece uma vez com o motivo, e dois turnos seguidos dão **o mesmo texto** (estabilidade da cache).
3. `_sem_erro_apos_escalar` com `escalados` de turnos anteriores.
4. Teste de engine com API falsa: conversa com tarefa `escalar` → o `system` enviado contém a nota.

## Medição depois do deploy (mesma consulta de 08/10)
Alvo: turnos que repetem `escalar_para_humano` depois da escalada **de 74% para <15%**, latência mediana
desses turnos perto de 2–3 s, `sem_texto` a 0. Se a Inês continuar a repetir apesar da nota, passar a
retirar só `escalar_para_humano` (não o `guardar_dados_cliente`) para conversas com um único motivo.

## Risco
- Prompt de todos os assistentes tem uma frase extra em conversas escaladas: baixo (só texto). A nota diz
  «só chamas tools se surgir um assunto novo», por isso um 2.º motivo da Maria continua a escalar.
- Cache: 1 miss por conversa escalada; medir.
- Sem migration. Reversível com `git revert`.

## Decisões (08/10)
1. ~~Nota suave vs retirar tools~~ — **decidido: nota suave** (P2); as tools ficam.
2. ~~Que assistentes~~ — **decidido: todos os que escalam** (mesmo código).
3. ~~Texto da nota~~ — **decidido: o proposto em P2.**

**Estado: plano fechado a 08/10. Por implementar.**
