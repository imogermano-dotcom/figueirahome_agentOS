# Incidente — seis dias de WhatsApp mudo (24 a 29 de Agosto de 2026)

## O sintoma, e a leitura errada

De 24 a 29/08 ninguém respondeu à Matilde. Com os templates a sair na hora e a
`quality_rating` a GREEN, a leitura natural foi *"as pessoas não estão a
responder"* — e a discussão andou à volta do conteúdo da mensagem.

Estava errada. **As mensagens não chegavam a ninguém.**

## A causa

O cartão do método de pagamento da conta WhatsApp Business (WABA) expirou. O erro
**`131042`** da Meta comporta-se assim:

1. a Graph API devolve **`200`** com `message_status: "accepted"`;
2. a mensagem **nunca é entregue**;
3. a **`quality_rating` não é afectada** — fica GREEN;
4. o `status` do número fica **CONNECTED** e o `account_mode` **LIVE**.

Ou seja: todos os indicadores que se costumam consultar continuam verdes.

## Porque não demos por isso

`channels/whatsapp/webhook.py` lia **só** `value["messages"]`. A Meta manda os
recibos de entrega — `sent`, `delivered`, `read`, **`failed`** com código de erro
— em `value["statuses"]`, e nós respondíamos `200` e deitávamos fora.

**`200 accepted` quer dizer "aceite para envio", nunca "entregue".** O n8n marca
`template_enviado_em` com base nesse `200`, portanto a base registou como
contactadas 45 leads que nunca receberam nada.

## Como se diagnosticou sem ler o corpo dos recibos

Contando os `POST /webhook/whatsapp` nos logs do Fly por cada envio:

| envio | recibos | significado |
|---|---|---|
| antes do cartão trocado | **1** | estado terminal imediato = `failed` |
| depois, com o `v55` | **3** | `sent` → `delivered` → `read` |

Uma mensagem entregue produz sempre pelo menos dois. Um só, a chegar ~20 s depois
do envio, é uma falha.

## O corte nos dados

| dia | templates marcados | responderam |
|---|---|---|
| 22/08 | 19 | 7 |
| 23/08 | 22 | **5** |
| 24/08 | 16 | **0** |
| 25–29/08 | 29 | **0** |

Última resposta de uma lead: **2026-08-23T21:17**.

## A correcção

`webhook.py` passa a tratar `value["statuses"]`. Falha sai como `ERROR` com o
código e o detalhe da Meta; o resto a `INFO`. Só log — sem tabela e sem
migration: o que faltava era **conseguir ver**.

```
WhatsApp NAO ENTREGUE a 351914590925 — codigo 131042:
Business eligibility payment issue | Failed to send message because of payment issue
```

`errors` ausente não rebenta: um `KeyError` aqui devolvia `500`, e a Meta lê `500`
como falha nossa e reenvia em ciclo.

## Verificação, 2026-08-29

Ponta a ponta, com o número do próprio utilizador (`351914590925`):

| troço | resultado |
|---|---|
| Envio → Graph API | `200 accepted` |
| Meta → telefone | ✅ recebido |
| Meta → nosso webhook | ✅ `sent` + `delivered` + `read` |
| Telefone → motor → resposta | ✅ |

## O que fica por resolver

**As 45 leads.** Estão `contactada` com `template_enviado_em` preenchido e nunca
receberam nada. O backfill `02` não as apanha (filtra `template_enviado_em
is.null`) e o follow-up `03` mandar-lhes-ia a segunda mensagem sem ter havido
primeira, marcando-as `sem_resposta` — que é falso, nunca lhes perguntámos nada.

Reenvio: `template_enviado_em` a `NULL`, `estado` a `nova`, e `02` com `Limit=5`.
**Antes disso, confirmar no WhatsApp Manager → Insights a data exacta** em que
*entregues* caiu a zero: 24/08 é inferência a partir da ausência de respostas, e
se algumas desse dia chegaram mesmo, limpar tudo manda-lhes mensagem repetida.

**Prazo: 23/09.** `guards._JANELA_LEAD_DIAS = 30`, contado de `criado_em`. Passada
a janela, quem responder deixa de cair na Matilde e vai para a Maria sem o
`imovel_ref` do anúncio.

**`name_status: DECLINED`.** O nome do número foi recusado pela Meta. Quem não
tenha o contacto gravado vê um `+351 9xx` cru em vez de "Imogermano" — e uma
mensagem fria de um número sem nome lê-se como spam. Não bloqueia o envio.

**O `01` a disparar com 12h de atraso** desde 28/08: os templates passaram a sair
em rajada de manhã em vez de quando a lead entra. Como **16 das 17 respostas
reais vieram na 1.ª hora** (máx. 1,3 h), isto sozinho chega para matar a
conversão.

**`logging.basicConfig(level=logging.INFO)`** por pôr no `main.py`. Sem ele a raiz
fica em `WARNING`: o `ERROR` da falha aparece, mas `sent`/`delivered`/`read`
ficam invisíveis e só se inferem pela contagem de recibos.

## Lições

- **Verde não é entregue.** `quality_rating`, `status` e `account_mode` não dizem
  nada sobre faturação. Quando a Matilde emudecer, **ver a faturação da WABA
  antes de discutir o conteúdo da mensagem**.
- **Um `200` de uma API de mensagens raramente significa o que parece.** Aqui
  significa "aceite para envio", e foi com base nele que se escreveu na base.
- **Silêncio prolongado é uma avaria até prova em contrário.** Seis dias de zero
  respostas depois de dias com cinco e sete não é comportamento humano.
