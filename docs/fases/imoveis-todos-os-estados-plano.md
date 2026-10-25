# Imóveis: todos os estados pela API nova (plano, pedido #45 do Miguel)

> Estado 25/10: **só plano, nada implementado.** Decisões 1–4 tomadas a 25/10 (as propostas do plano, ver fim). Pedido original e proposta do Miguel (19/10) em `SYNC_IMOVEIS_DEV_PROPOSTA.md` (fora do repo).

## Problema

`imoveis` só recebe alterações dos imóveis **publicados no site**: o sync (`imoveis_sync.sync_egorealestate_api`) lê a Web API pública
(`websiteapi…`), que só lista publicados. Um imóvel que muda de estado e não está (ou já não está) no site fica com o estado antigo; os que
nunca foram publicados (Prospecção, Por validar) nunca entram. A validação CRM por scraping (`validar_disponibilidade_crm`) só corre à mão
e só para os refs que saíram da Web API.

### Medição de 25/10 (API nova `ListRealestateByPage`, só leitura)

- eGO: 5 159 referências (5 163 linhas, 4 repetidas). Supabase: 4 469.
- **705 do eGO não existem no Supabase**: Em Prospecção 520, Retirado 63, Por validar 61, Vendido 50, Arrendado 7, Disponível 2 (APA_5495, o teste do
  Miguel, e APA_5473), Reservado 2.
- **7 com o estado diferente** (FH2573 Vendido→«Por validar», FH2483_B Disponível→«Retirado», FH2580 Arrendado→«Reservado», FH2571, FH2574, FH2552,
  FH2491). Cinco têm `fonte='egorealestate'`, duas `manual` (FH2483_B, FH2491).
- **94 com `lastUpdate` do eGO posterior ao `ego_atualizado_em` do Supabase.**
- Disponíveis: eGO 64, Supabase 61. A FH2371 do pedido já está certa porque entretanto foi publicada no site; o problema mantém-se para o resto.

## Desenho

Novo sync **a seguir** ao da Web API, que não se altera: `sync_imoveis_todos` em `imoveis_sync.py`.

1. **Ler tudo.** `POST /realestate/Realestate/ListRealestateByPage?applicationId=…` com `{pageIndex, numberOfRecords: 500}` (`pageIndex` a partir de 0)
   até vir menos de 500. ~11 pedidos, medido a 25/10. Sempre completo, como o resto dos syncs do eGO (`?Since=` é pouco fiável); incremental por
   `minDateAltered` só se o tempo o exigir. Levanta se a contagem não bater com `totalRows` (nunca comparar com dados parciais).
2. **Uma linha por referência.** O mesmo `reference` pode ter vários registos internos (FH2483_A: 3). Fica o de `lastUpdate` mais recente com
   `fieldStatusId = 0`; empate pelo `id` maior.
3. **Estado.** `realestateStatusId` → `disponibilidade`: 2 Disponível, 3 Vendido, 4 Reservado, 5 Arrendado, 7 Em Prospecção, 8 Retirado, 9 Por validar
   (confirmado pelos 5 159 casos de 25/10; um código novo é ignorado e conta em `desconhecidos`).
4. **Ligar por referência**, nunca por id: o `ego_id` do Supabase é o `metabaseId` da Web API; o `id` da API nova é outro e muda (FH2573 passou de
   26134108 para 30216152). O sync não escreve `ego_id`.

### Regras de coexistência com a Web API (o ponto que não pode falhar)

`publicado` é uma coluna **GENERATED**: `disponibilidade = 'Disponível'` **e** preço > 0 **e** `disponivel_na_api`. Um imóvel Disponível inserido com
`disponivel_na_api = true` (o valor por omissão) apareceria no site sem estar publicado (o APA_5495 tem 100 000 € e está Disponível).

- **Imóvel que a Web API vê** (`disponivel_na_api = true` na última pull): a Web API manda. O sync novo **não escreve**; se o estado divergir (FH2574,
  FH2552), regista a divergência no resumo para se ver à mão.
- **Imóvel inserido pelo sync novo:** `fonte='egorealestate'`, `disponivel_na_api = false`. Nunca fica `publicado`.
- **Imóvel existente que a Web API não vê** (`disponivel_na_api = false`, ou que saiu): o sync novo atualiza `disponibilidade` e `ego_atualizado_em`
  (`lastUpdate`). Não toca em `disponivel_na_api`.
- **`fonte='manual'` (≈4 000):** não se tocam. As duas divergências manuais (FH2483_B, FH2491) só aparecem no resumo. *Decisão 3.*
- **Nunca se apagam linhas.** O `validar_disponibilidade_crm` fica como está.

### Colunas das linhas novas (mínimo útil, só o que a lista dá)

`imovel_ref`, `disponibilidade`, `fonte`, `disponivel_na_api=false`, `ego_atualizado_em`, `data_criacao`/`data_alteracao` (`createDate`/`lastUpdate`),
`titulo` (`name['PT-PT']`), `quartos` (`rooms`), `casas_banho` (`bathrooms`), `area_util` (`nettArea`), `area_bruta` (`grossArea`),
`area_terreno` (`landArea`), `venda_preco`/`arrendamento_preco` (de `businesses[].prices[0].value`; `businessTypeId` 1 venda, 2 arrendamento).
Fica de fora (fase 2): `natureza` (precisa de tabela `natureTypeId`), `angariador` (precisa de `ListEmployees`), localização, fotos, features.
Sem coluna nova nem migration. As comissões continuam fora (a API devolve-as a zero: pedido #41).

### Armadilhas conhecidas

- **Upsert por lotes do PostgREST:** uma chave presente num só registo vira coluna e escreve NULL nos outros. Todas as linhas inseridas têm exatamente as
  mesmas chaves; as atualizações de estado vão por UPDATE por `imovel_ref`, nunca por upsert de lote.
- **Escrita em linhas do eGO que a Web API vê:** proibida (regra acima), é o que evita flip-flop entre os dois syncs.
- **Painel e portal do Miguel** leem `imoveis`: +705 linhas. O painel de Imóveis abre filtrado em «Disponível»; confirmar antes de ligar que nenhum
  contador usa o total da tabela (imóveis contam-se por `publicado`, ver CLAUDE.md).

## Endpoint e cron

`POST /api/imoveis/sync/egorealestate/todos` (`X-Sync-Secret`, cron/manual) com `?dry=1` que lê, compara e devolve as contagens **sem escrever**.
Resumo em `agente_sync_log` (`egorealestate_imoveis_todos`); falha de cron → email como os outros syncs. Cron diário `sync-imoveis-todos` às 06:47 UTC
(depois do `sync-imoveis-manha` das 06:17), **`enabled: false` até à 1.ª passagem aprovada.**

## Testes

Mapeamento de estado (os 7 códigos, desconhecido ignorado); uma linha por referência (repetidas, `fieldStatusId`); página incompleta levanta;
imóvel visto pela Web API não é escrito e a divergência vai para o resumo; imóvel novo entra com `disponivel_na_api=false` e **não** fica `publicado`
(teste sobre a regra, com um Disponível com preço); existente não visto atualiza estado e data; `fonte='manual'` nunca é escrito; `dry` não escreve;
as chaves das linhas inseridas são idênticas; nenhuma linha é apagada.

## Passos (cada escrita em produção só com ordem expressa)

1. Decisões abaixo; avisar o Miguel (pedido, ponto 8) antes da 1.ª passagem real.
2. Código + testes; deploy com o cron desligado.
3. **Dry-run em produção** (`?dry=1`): contagens a confirmar com as de 25/10 (705 a inserir, 7 divergentes, 94 mais recentes).
4. 1.ª passagem real com ordem tua; verificar que `publicado` não mudou (49) e que o site não mudou.
5. Ligar o cron.
6. Docs: CLAUDE.md, `database-schema.md` e este plano.

## Decisões (25/10, as propostas do plano)

1. **Inserir todos** os 705, incluindo os 520 em Prospecção, com `disponivel_na_api=false` (pedido do Miguel: «incluindo os em Prospecção»).
2. **Cron diário às 06:47 UTC**, desligado até à 1.ª passagem aprovada.
3. **Linhas `fonte='manual'` com divergência** (FH2483_B, FH2491): só aparecem no resumo.
4. **Fase 2** (natureza, angariador, localização) fica para depois.
