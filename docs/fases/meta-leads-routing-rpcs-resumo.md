# Resumo — WhatsApp multi-número, routing de leads Meta e bug nas 3 RPCs (25/09)

Pedido inicial: preparar suporte a um 2º número WhatsApp. Isso levou a testar
o fluxo `Meta leads to supabase` (n8n) com o "Enviar lead de teste" do Meta,
o que expôs três bugs reais em produção, nunca antes exercitados por dados
reais.

## 1. WhatsApp multi-número (pré-requisito)

`meta_api.py`/`webhook.py` respondiam sempre pelo número único de
`META_PHONE_NUMBER_ID`, ignorando por qual número a mensagem tinha entrado
(`value.metadata.phone_number_id`, presente no payload da Meta). Com 2+
números na mesma app isso faria a resposta sair sempre pelo antigo.

Fix: `phone_number_id` capturado no webhook, passado a
`send_text_message`/`mark_as_read`, com fallback para o número único de
sempre quando falta. Retrocompatível, sem migration.

## 2. Routing de leads orgânicas/de teste

`Switch campanha` (workflow `9DQlBhON12R1Pane`) decidia o ramo (Angariação/
Recrutamento/Compra) só por `campaign_name` — campo que a Graph API omite em
leads **orgânicas ou de teste** (`is_organic: true`, sem anúncio pago). Essas
leads caíam sempre no ramo de Compra por omissão, corriam a RPC errada e
devolviam erro.

- Novo nó `Filtrar leads de teste` (IF) descarta leads dummy do "Enviar lead
  de teste" (assinatura: `field_data` contém `"test lead: dummy data for"`).
- `Switch campanha` ganhou condição OR pelo nome do formulário
  (`Meta Form Name`, sempre presente, orgânico ou não) — não só `campaign_name`.
- `Webhook.responseMode`: `lastNode` → `onReceived`. Make deixa de ver
  qualquer erro interno do n8n (responde 200 assim que recebe); a Make só
  faz de router entre Meta e n8n, como já era a intenção.

## 3. Bug nas 3 RPCs (`lead_meta_compra`/`recrutamento`/`angariacao`)

Confirmado ao vivo com leads reais (Sandra Nascimento, recrutamento):

- **`tipo_contacto = tipo_contacto || 'x'`** — `array[] || text` é ambíguo no
  Postgres quando o texto é um literal simples; tentava ler `'recrutamento'`
  como literal de array e falhava (`malformed array literal`). Só acontecia
  no branch de **contacto já existente** ("linked") — novo ("created") não
  passa por ali. Fix: `array_append`.
- **`meta_lead_id` nunca gravado no branch "linked"** — só o INSERT o grava.
  O sub-fluxo de envio de template procura o contacto por `meta_lead_id`;
  sem ele, 0 resultados, 0 template enviado, sem erro nenhum. Qualquer lead
  da Meta que batesse com um contacto já existente (scraper/eGO — comum)
  nunca recebia WhatsApp, silenciosamente, desde sempre. Fix: `meta_lead_id`
  (e `meta_form_name`/`meta_created_at`) passam a **substituir sempre**, não
  só quando vazios.

Ambos corrigidos nas 3 RPCs (mesma origem, copiadas juntas em 17/09).
Confirmado ao vivo: Sandra Nascimento recebeu o template depois do fix.

## Por fazer

- Confirmar o nome real do formulário de Angariação no Meta (só recrutamento
  foi confirmado — "FRM RECRUTAMENTO") para reforçar o fallback do Switch
  nesse ramo também.
- Testar o 2º número WhatsApp real quando o utilizador o registar no Meta
  Business Manager (mesma app/WABA → nada a mudar no webhook; app diferente
  → repetir o Callback URL lá).
