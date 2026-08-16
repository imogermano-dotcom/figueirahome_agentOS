# Fluxos n8n — leads da Meta

O elo do meio do fluxo das leads pagas. Do lado do backend está tudo construído
e deployado; o que falta é isto.

```
Meta Lead Ads → Make (escreve em `leads`) → webhook → n8n (envia o template)
              → a lead responde → webhook do WhatsApp → o A1 assume
```

| Ficheiro | O quê | Estado |
|---|---|---|
| `01-enviar-template.json` | envia o template e marca a lead | pronto a importar |
| follow-up 48h | segunda tentativa a quem não respondeu | por construir — ver no fim |

## Antes de importar

**1. Template aprovado na Meta.** Mensagens iniciadas pelo negócio exigem um
template pré-aprovado no Business Manager. Sem isso a Graph API recusa. O nome
dele entra no nó *Meta: enviar template*, em `NOME_DO_TEMPLATE_APROVADO`.

**2. Credenciais no cofre do n8n, nunca no corpo dos nós.** Assim não aparecem
em exports do workflow nem nos logs de execução.

**Supabase → credencial *Custom Auth*** (não *Header Auth*: essa só aceita um
par nome/valor, e o PostgREST quer dois):

```json
{
  "headers": {
    "apikey": "<SERVICE_ROLE_KEY>",
    "Authorization": "Bearer <SERVICE_ROLE_KEY>"
  }
}
```

Nos nós HTTP: *Authentication* → Generic Credential Type → Custom Auth.

Tem de ser a **`service_role`**: `leads` tem RLS com política `to authenticated`
apenas, e a `anon` não lê nem escreve lá. Consequência a ter presente — é mais um
sítio com a chave que ignora o RLS em toda a base, além do Make.

Alternativa: o nó nativo **Supabase** (credencial *Host* + *Service Role
Secret*), trocando os dois nós HTTP por *Get a row* e *Update a row*. Trata dos
headers sozinho; é menos explícito sobre o que vai no pedido.

**Meta → *Header Auth*** com `Authorization` = `Bearer <META_WHATSAPP_TOKEN>`.
Se usares o nó nativo do WhatsApp, é a credencial dele (token + Business Account
ID) e este ponto não se aplica.

**3. Variáveis de ambiente** no n8n: `SUPABASE_URL` e `META_PHONE_NUMBER_ID`.

### Identificadores da conta WhatsApp (confirmados 2026-08-16)

| | |
|---|---|
| Phone number ID | `925368620661613` |
| Número | +351 928 318 953 — nome verificado "Imogermano" |
| Webhook configurado na Meta | `https://figueirahome-agentos.fly.dev/webhook/whatsapp` |
| Token | system user `fighome_agent`, **não expira** (`expires_at: 0`) |

**O WhatsApp Business Account ID (WABA) não está guardado no projecto** — o
backend não precisa dele, só o nó do n8n (para listar os templates). Encontra-se
em developers.facebook.com → a app → **WhatsApp → API Setup**, mesmo por cima do
Phone number ID; ou em Business Settings → Contas → Contas do WhatsApp.

Não dá para o tirar do token: o system user tem os scopes mas o WABA está
atribuído pelo negócio, e `assigned_whatsapp_business_accounts` vem vazio.

O webhook apontar para o nosso backend é a confirmação de que este é o número
que o A1 escuta — enviar o template por outro faz a resposta da lead nunca
chegar.

**4. O `phone_number_id` tem de ser o mesmo** que o backend escuta. Se o template
sair de outro número, a resposta da lead nunca chega ao A1 e a conversa morre
sem dar sinal.

## Do lado do Make

Módulo **HTTP → Make a request**, a seguir ao que escreve em `leads`:

| Campo | Valor |
|---|---|
| URL | `https://<n8n>/webhook/lead-nova` — **produção**, não `/webhook-test/` |
| Method | `POST` · Body type Raw · Content type JSON |
| Request content | `{"meta_lead_id": "{{id do lead vindo da Meta}}"}` |

**`meta_lead_id` e não o `id` da linha**: o PostgREST só devolve o registo criado
se a inserção mandar `Prefer: return=representation`; sem isso responde `204` sem
corpo e o Make fica sem id para passar adiante. O `meta_lead_id` o Make já o tem
do webhook da Meta, antes sequer de escrever, e a coluna é `UNIQUE`.

**Autenticar o webhook.** Sem isso, quem descobrir o URL dispara envios de
template do vosso número — custa dinheiro e estraga a *quality rating*. O nó
Webhook aceita Header Auth; o Make manda o header.

## O que o fluxo faz

1. **Webhook** — o Make chama com `{"meta_lead_id": "…"}`. A linha é lida a
   seguir na base, para não depender do formato do Make.
2. **Lê a lead** no Supabase.
3. **Guardas** — três, e todas importam:
   - `tipo` em `compra`/`arrendamento`. Angariação segue o fluxo humano.
   - tem telefone.
   - `template_enviado_em` vazio. **Idempotência**: o Make pode repetir o
     webhook, e sem isto a pessoa recebia a mensagem duas vezes.
4. **Prepara** o texto renderizado e o número em E.164.
5. **Envia** pela Graph API.
6. **Marca** `template_enviado`, `template_enviado_em` e `estado='contactada'`.

Se a Meta falhar, o nó aborta e a lead fica `nova` — a retentativa apanha-a.

## Três armadilhas

**O `template_enviado` tem de ser o texto renderizado**, com as variáveis já
substituídas — não o nome do template nem `Olá {{1}}`. É esse texto que o
backend injecta no histórico como mensagem do assistente. Se lá for o nome do
template, o A1 lê isso como algo que disse.

**O texto vive em dois sítios**: aprovado na Meta, e copiado no nó *Preparar
texto e número*. A Graph API recebe só os parâmetros, não devolve o texto final
— a duplicação é inevitável. **Se mudares o template na Meta, muda aqui também**,
senão o histórico do A1 passa a mentir.

**Nunca escrever `respondeu_em`.** Essa coluna é do backend, e é o sinal de que a
pessoa falou. Se o n8n a escrever, o follow-up deixa de saber quem respondeu.

## O que o n8n escreve, e o que não escreve

| Coluna | Quem |
|---|---|
| `template_enviado`, `template_enviado_em`, `estado='contactada'` | **n8n** |
| `respondeu_em`, `conversa_id` | backend, quando a lead fala |
| `estado='qualificada'`, `qualificada_em` | backend, quando o MQL fica completo |

## Follow-up às 48h — por construir

A query já é trivial e inequívoca, graças à `0027`:

```sql
select id, nome, telefone, template_enviado_em
from leads
where respondeu_em is null
  and template_enviado_em < now() - interval '48 hours';
```

Quem está a falar com o A1 fica de fora automaticamente.

**Falta uma decisão e uma coluna.** A decisão: segunda mensagem, ou tarefa para
alguém ligar? A coluna: sem registar que o follow-up saiu, um *Schedule Trigger*
diário reenvia à mesma pessoa todos os dias. É uma migration de uma linha
(`follow_up_em timestamptz`) — digam quando decidirem o resto e faço.
