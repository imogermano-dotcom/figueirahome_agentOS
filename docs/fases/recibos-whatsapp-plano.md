# Recibos de entrega do WhatsApp — plano

> Fase nova. **Plano antes de código** (CLAUDE.md, regra 2). Nada implementado.
> Versão com **colunas em `contactos`** (decisão de 16/10: uma tabela de recibos por mensagem seria mais do que o problema pede).

## Porquê
`200 accepted` da Graph API não é entrega. O n8n marca `template_enviado_em`/`follow_up_em` com o 200: durante 6 dias marcou 45 leads
como contactadas que nunca receberam nada (CLAUDE.md, invariantes). A Meta diz a verdade depois, no webhook, em `statuses`:
`sent` → `delivered` → `read`, ou `failed` com código de erro. O backend já recebe esses eventos (`webhook.py:89`,
`_registar_estado`) mas **só os escreve num log**: `failed` em ERROR (visível ~30 min no Fly), `delivered`/`read` em INFO (invisível,
a raiz está em WARNING). Verificado a 16/10 com a lead de compra `…790`: dois webhooks 2 e 4 s após o envio, sem linha de erro, mas
sem prova de `delivered`. O objetivo é saber, **por contacto**, se o número recebe WhatsApp, e deixar os fluxos de follow-up saltar quem não recebe.

## O que a Meta manda (por evento)
`id` (wamid), `status`, `timestamp` (unix), `recipient_id` (telefone com indicativo) e, só em `failed`, `errors[]`
(`code`, `title`, `error_data.details`). Os eventos de uma mensagem podem chegar fora de ordem. Os dos envios do n8n chegam ao mesmo
webhook que os dos assistentes (POSTs de 16/10 às 15:12:56/58, logo após o envio do fluxo de follow-up).
- `failed` **131026** = mensagem não entregável: sem WhatsApp, número inativo, ou utilizador sem aceitar os termos. A Meta **não distingue** as causas.
- Outros `failed` **não** são sobre o número (131049 limite de marketing por pessoa, 131047 janela de 24 h fechada, 131030 número fora da lista de teste…):
  não devem marcar o contacto como sem WhatsApp. Ficam só no log, como hoje.
- `read` só chega se a pessoa tiver os recibos de leitura ligados: ausência de `read` não é falha.

## Desenho
Migration `0048` (aditiva, nullable, mesmo padrão da `0044`/`0045`/`0047`; o scraper, o pipeline do Miguel e as RPCs `lead_meta_*` não as tocam):

```sql
alter table public.contactos
  add column if not exists whatsapp_entregue_em timestamptz,   -- último 'delivered'/'read' para este número
  add column if not exists whatsapp_falhou_em   timestamptz,   -- último 'failed' PERMANENTE (131026)
  add column if not exists whatsapp_erro_codigo integer;       -- código desse failed
```

**Escritor — o webhook** (`channels/whatsapp/webhook.py`, `_registar_estado`), em `background_tasks` (o handler é async, o cliente Supabase é síncrono),
com try/except: **uma falha ao gravar nunca estraga o 200 à Meta**. Função pura `_efeito_do_estado(estado) -> dict | None` (testável sem rede):

| Evento | Efeito em `contactos` (linhas cujo `telefone` ou `telemovel` bate nas variantes de `recipient_id`) |
|---|---|
| `delivered` / `read` | `whatsapp_entregue_em` = timestamp do evento; **limpa** `whatsapp_falhou_em` e `whatsapp_erro_codigo` |
| `failed` com código na lista permanente (`{131026}`) | `whatsapp_falhou_em` = timestamp; `whatsapp_erro_codigo` = código |
| `failed` com outro código, `sent` | só log (como hoje) |
| mensagem **recebida** do número | limpa `whatsapp_falhou_em`/`whatsapp_erro_codigo` (quem escreve tem WhatsApp) |

- Telefone: `guards.normalizar_telefone` + `guards.variantes_telefone`; filtro `or` sobre `telefone`/`telemovel` (a tabela tem as duas colunas).
  O mesmo telefone existe em várias linhas (há ~10 000 duplicadas): marcam-se **todas** as do telefone.
- Eventos fora de ordem: só se escreve se o timestamp do evento for **mais recente** que o já gravado (`entregue_em` vs `falhou_em`).
- `contactos` tem um `BEFORE INSERT OR UPDATE` (`tgr_normaliza_origem_contactos`, `0042`) que só normaliza `origem`; um UPDATE destas colunas passa por ele sem efeito.
  Confirmar com a primeira escrita real. Outros *triggers* criados à mão no Supabase não se veem no repo (o esquema não é fonte única): verificar com `\d`/painel antes de ligar.
- **Escritas por RPC não**: aqui é UPDATE com filtro, linha a linha por telefone, não upsert em lote (invariante do PostgREST sobre colunas esparsas).

**Leitura**
- `scripts/entrega_whatsapp.py` (só leitura): contactos com `template_enviado_em`/`follow_up_em` nos últimos N dias e o estado de cada um
  (`entregue` / `falhou` / **sem recibo**); saída com contagens por código e telefones só com os últimos 3 dígitos.
- Fase 2 (separada, depois de medir): o filtro do nó "Ler contactos sem resposta" ganha `whatsapp_falhou_em=is.null`, e o painel mostra "sem WhatsApp".
  Exige editar o n8n; **não** entra nesta fase.

## Segundo caminho de falha: rejeição imediata (número mal formado)
O webhook só vê o que a Meta aceitou. Um número mal formado (curto, com letras, sem indicativo) é recusado **no próprio envio**, com 400, e nunca gera `statuses`.
Verificado a 16/10 nos fluxos (só leitura):
- Os nós de envio (`Send template` no fluxo `4rDc9amm6HpO5F4j`; `WhatsApp: enviar follow-up` no `TK8moXEAjYgvrY1A`) **não têm** `onError`/"continue on fail":
  o erro pára a execução. O contacto **não** é marcado (a marcação vem depois do envio), por isso continua elegível.
- Consequência no follow-up diário: a leitura ordena por `template_enviado_em asc` com Limit 5, em lote. **Um número mau à cabeça pára a execução todos os dias
  e bloqueia os contactos seguintes**, sem ninguém avisado (só aparece em Executions). Nos fluxos de template (uma lead por execução) falha só essa lead.
- Em 16/10 não há execuções com erro no fluxo de template (`4rDc9amm6HpO5F4j`): o caso é real mas ainda não aconteceu aqui.

Proposta (n8n, **fase 2**, só depois de o utilizador aprovar a edição): no nó de envio, `onError: continueErrorOutput`; a saída de erro vai a um nó "Supabase: marcar
falha" que grava `whatsapp_falhou_em` = agora e `whatsapp_erro_codigo` = código da Graph API (ou um valor fixo, p. ex. `0`, quando for falha de rede), e **volta ao
"Uma de cada vez"**, para o lote continuar. Assim a rejeição imediata e o 131026 do webhook acabam na mesma marca, e o filtro `whatsapp_falhou_em=is.null` serve os dois.
Falhas de rede/Meta em baixo (5xx) **não** devem marcar o número: só 4xx de parâmetro inválido; distingue-se pelo código de estado no nó de erro.

## Alerta: quem é avisado
Hoje ninguém. A fase 1 grava a marca e o script permite consultar; **não avisa**. Acrescenta-se um aviso por email, no padrão de `notificacoes.falha_de_sync`
(diretor + `ALERTAS_PARA`), em **resumo diário** (não um email por falha): "N contactos sem WhatsApp nas últimas 24 h" com os códigos e os últimos 3 dígitos.
Corre no Cron Manager (`figueirahome-crons`, `schedules.json`) via endpoint com `X-Automacao-Secret`; só envia quando N > 0. Um cron que não arranca não é apanhado
(limitação já assumida nos syncs).

## O que se perde face a uma tabela (assumido)
- Sem histórico por mensagem nem linha do tempo `enviada → entregue → lida`; sem rácio entregue/enviada nem categoria de faturação.
- Um `failed` de um número que **não** tem linha em `contactos` (p. ex. uma resposta de assistente a quem só existe em `agente_clientes`) não tem onde ser marcado: fica no log.
- Não distingue "sem WhatsApp" de "número inativo" (a Meta também não).
- Se um dia fizer falta o histórico, cria-se a tabela por cima; estas colunas não atrapalham.

## Fora de âmbito
Não bloqueia nem corrige envios. Não muda os fluxos do n8n. Não altera `template_enviado_em`/`follow_up_em` (continuam a significar "o n8n tentou").
Não guarda texto das mensagens.

## Decisões por tomar
1. **Migration `0048`**: corres tu no editor SQL, depois de eu explicar. (O plano da API do eGO passa a `0049`.)
2. **Lista de códigos permanentes**: só 131026? Acrescentar mais códigos só com evidência (log real).
3. **Fase 2** (n8n e painel) quando a fase 1 tiver medições: saída de erro dos nós de envio, filtro `whatsapp_falhou_em=is.null`, estado no painel.
4. **Resumo diário por email**: entra na fase 1 (código + cron) ou só depois de medir? Recomendo na fase 1, é pouco código e é o que torna a marca visível.

## Testes
- `backend/tests/test_whatsapp_recibos.py`: `_efeito_do_estado` com `delivered`, `read`, `sent`, `failed` 131026 (efeito permanente), `failed` 131049 (sem efeito), evento sem `timestamp`,
  recipient com `351…`/`+351…`; telefones de teste `912345678`.
- Ordem: `failed` mais antigo que um `delivered` já gravado não marca; `delivered` mais novo limpa o `failed`.
- Mensagem recebida limpa a marca. Mock do cliente Supabase; sem rede.

## Medição depois do deploy
- Próximo envio real: `whatsapp_entregue_em` preenchido no contacto (prova de `delivered`). Para a `…651` (follow-up a 17/10 às 12h Lisboa).
- Contagem de contactos com `whatsapp_falhou_em` e códigos numa semana. Esperado: `failed` raro; se for >10% dos envios, o `200` do n8n está a mentir em escala e a fase 2 passa a prioritária.
- 0 erros de escrita do webhook no log (`_registar_estado`).

## Risco
Baixo: três colunas nullable, escritas só pelo webhook, falha isolada, nada lido por outros sistemas. Cuidado com o volume de UPDATEs em linhas duplicadas do mesmo telefone (poucas linhas por telefone, irrelevante à escala atual).

**Estado: plano reescrito a 16/10, nada implementado.**
