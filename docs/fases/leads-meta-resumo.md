# Leads da Meta + qualificação — resumo (2026-08-13/14)

Movido do `CLAUDE.md` por causa do limite de 200 linhas. As decisões desta fase
estão em `docs/decisoes.md`, secção "Leads da Meta".

## Sync eGO — `6ae84db`, `c449224`, `9838377` (deployados)

`_map_property` escrevia 25 de 60 colunas. Passou a preencher 11 booleanas de
features, `conservacao`, `certificacao_energetica`, `angariador`, `suites`,
`exclusividade`, datas, `piso` e `latitude`/`longitude`.

Três armadilhas que custaram dados reais e ficaram registadas em `decisoes.md`:
features do imóvel vs zona envolvente nas `FeatureTags`; o upsert por lotes do
PostgREST a escrever NULL em todos os registos quando uma chave só aparece num
(custou 40 coordenadas); e `latitude`/`longitude` só válidas com
`HasGPSLocation=true` (13 de 53 — sem o flag o eGO devolve o centróide da zona,
40 imóveis em 11 pontos).

## Leads da Meta — `85a3465`, `5746e79` (por deployar)

Make escreve em `leads` → n8n manda o template e chama
`POST /api/leads/{id}/conversa-semeada` → a thread nasce com
`agente='a1_vendedor'` e o template no histórico → a lead responde e o A1
continua.

Novos: `api/leads_meta.py`, `tests/test_leads_meta.py`, migration `0021`.
Editados: `guards.py`, `conversation.py`, `webhook.py`, `deps.py`.

Teste ao vivo: "Sim" seco → o A1 respondeu com 2 imóveis reais em Buarcos dentro
do orçamento, sem perguntar nada. 7,3 s, **$0,055** num turno com pesquisa.

## Qualificação — buraco fechado (2026-08-14, em `master`, por deployar)

A promoção só disparava de dentro de `find_or_create_cliente`, que exige que o
assistente escreva dados do cliente. Com o formulário da Meta a trazer já
orçamento + zona + tipo — o caso normal — o A1 não tinha nada para escrever,
nunca chamava, e a lead ficava `contactada` para sempre: o corretor nunca era
avisado.

`guards.promover_se_qualificada`, chamada ao fim de cada turno de
`engine.responder` com telefone. Aceita `nova` além de `contactada`, porque aí o
turno é prova directa de que a pessoa respondeu — apanha quem escreve sem nunca
ter recebido template (`whatsapp_permissao` está a `True` em 3 de 79). O gatilho
antigo mantém-se em `contactada` apenas: por lá passa a semeadura, antes de a
pessoa dizer nada.

Custo: uma leitura indexada extra a `agente_clientes` por turno de WhatsApp,
contra um turno medido em 7,3 s. 4 testes novos em `test_leads_meta.py`.
