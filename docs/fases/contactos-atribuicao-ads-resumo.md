# Resumo — atribuição de anúncio Meta em `contactos` (28/09)

Pedido: analisar qualidade das leads/anúncios Meta. `contactos` ganhou
`ad_id`/`ad_name`/`adset_id`/`adset_name`.

Achado: o nó `Meta Lead Info` (Graph API, workflow n8n "Meta leads to
supabase") já pedia estes 4 campos à Meta — só nunca eram usados a partir
daí. Não foi preciso mudar a chamada à API da Meta.

## Feito

- `supabase/migrations/0045_contactos_ad_attribution.sql` — 4 colunas novas,
  aditivo, sem backfill.
- 3 RPCs (`lead_meta_compra`/`recrutamento`/`angariacao`) ganharam 4
  parâmetros novos (`default null`, retrocompatível), gravados em ambos os
  branches (insert novo e update "linked"), sempre sobrescritos — mesmo
  padrão de `meta_lead_id`/`meta_form_name`/`meta_created_at`. SQL corrido
  pelo utilizador no editor; confirmado via OpenAPI spec do PostgREST que os
  4 parâmetros novos estão registados.
- n8n: 3 Set nodes (`DADOS FB FORM Venda`/`Angariação`/`Recrutamento`)
  ganharam os 4 campos, lidos de `$('Meta Lead Info').item.json` (já
  disponível — `Venda` já lia `adset_name` para calcular `ref_imovel`,
  reaproveitado). 3 HTTP Request (`Supabase: criar lead *`) passaram a
  mandar `p_ad_id`/`p_ad_name`/`p_adset_id`/`p_adset_name` no `jsonBody`.
  Validado (`n8n_validate_workflow`, 0 erros).

## Limitação aceite

Campo sempre sobrescrito quando liga a um contacto já existente — só fica o
anúncio da submissão mais recente, sem histórico de exposição a vários
anúncios. Consistente com o resto dos campos `meta_*`; não pedido histórico.

## Por fazer

- Testar com lead real (ou "Enviar lead de teste" do Meta) e confirmar via
  REST que `contactos.ad_id`/`ad_name`/`adset_id`/`adset_name` ficam
  preenchidos.
