# Leads Meta → n8n nativo + `contactos` como registo unificado — resumo (14–17/09)

> Trabalho feito por sessões de chat directo no n8n (MCP) e SQL corrido à mão
> no Supabase pelo utilizador — sem plano prévio, iterativo. Este documento é
> o registo depois do facto, para o handoff.

## O que mudou

O fluxo `Meta leads to supabase` (n8n, `9DQlBhON12R1Pane`) substitui o antigo
módulo do Make que escrevia leads directamente em `leads`. Agora: **Make só
passa o ID da lead** (`POST /webhook/lead-nova-make`, corpo = ID em bruto), o
n8n vai buscar os dados à Graph API e decide o resto.

**`Switch campanha`** substitui o antigo `If1` binário — 3 saídas por
`campaign_name`: `Angariação` (`.includes('Angariação')`, case-sensitive, como
sempre foi), `Recrutamento` (`.toLowerCase().includes('recrutamento')`,
propositadamente insensível a maiúsculas — o nome da campanha "poderá mudar
para RECRUTAMENTO"), e fallback `Compra/Arrendamento` (tudo o resto).

Cada ramo chama uma função Postgres dedicada, `SECURITY DEFINER`, com dedup
gracioso (devolve `{"status":"duplicate",...}` em vez de rebentar):

| Ramo | Função | Escreve em | `tipo_contacto` |
|---|---|---|---|
| Compra/arrendamento | `lead_meta_compra` | `leads` **e** `contactos` | `comprador` |
| Angariação | `lead_meta_angariacao` | só `contactos` | `vendedor` |
| Recrutamento | `lead_meta_recrutamento` | só `contactos` | `recrutamento` |

**`lead_meta_angariacao` é o antigo `lead_meta_compra`, renomeado** — era uma
cópia esquecida e sem uso de `importar_lead_meta` (que continua viva,
intocada, nada mais lhe aponta). Aproveitou-se para não mexer na função em
produção. O nome ficou trocado por acidente histórico: apesar do nome,
"compra" aqui sempre quis dizer *a agência a angariar (comprar o mandato)*,
não o comprador do imóvel — daí a troca de nomes a meio da sessão.

## `contactos` ganhou 6 colunas novas

```sql
ALTER TABLE contactos
  ADD COLUMN estado text,
  ADD COLUMN template_enviado text,
  ADD COLUMN template_enviado_em timestamptz,
  ADD COLUMN meta_lead_id text UNIQUE,
  ADD COLUMN meta_form_name text,
  ADD COLUMN meta_created_at timestamptz,
  ADD COLUMN tipo_contacto text[];
```

Aditivo, 28 401 linhas existentes ficam `NULL`. **`contactos` é a tabela do
Miguel/pipeline externo** — só se mexeu por ser aditivo; nada de reestruturar
a coluna `tipos` já existente (livre, sem `CHECK`, valores heterogéneos como
`'Potencial Cliente'`, `'form'`, `'recrutamento_relatorio'`) — isso ficou
registado como conversa a ter com ele, não decisão unilateral.

Lógica das 3 funções, ramo "contacto não encontrado" (por telefone
normalizado, senão email): cria linha nova em `contactos`, `estado='nova'`,
`criado_em=current_date` (hoje, não a data da lead na Meta). Ramo "já existe":
só preenche campos vazios (nunca sobrescreve), `whatsapp_permissao` só liga
nunca desliga, e **não** grava `meta_lead_id`/`meta_form_name`/
`meta_created_at` — esses campos identificam a submissão que *criou* o
contacto, não a mais recente. `tipo_contacto` acrescenta a etiqueta se ainda
não lá estiver (um contacto pode ser `['comprador','vendedor']`).

## Buraco conhecido, não fechado

No ramo "liga a existente", como `meta_lead_id` não é gravado, **qualquer
fluxo a jusante que procure o contacto por esse `meta_lead_id` não encontra
nada**. Hoje isto só importa para Angariação — o fluxo de envio de template
(`FigueiraHome — enviar template Angariação`) está desenhado para **não
avançar** nesse caso (sem `alwaysOutputData` no `Ler lead angariação no
Supabase`: 0 linhas = 0 items = `Guardas` nem corre = não envia). Decisão
explícita do utilizador, não workaround. Confirmado ao vivo com uma lead real
(`Cristina Maria Ferreira`, `2212506922872316`, já em `leads_angariacao` com
`estado: follow_up` — nunca chegou a `contactos`, o teste parou correctamente
sem enviar nada).

## Fluxo `01` (`FigueiraHome — enviar template à lead da Meta`)

Ganhou `Execute Workflow Trigger` a par do `Webhook` do Make — depois
descobriu-se que o Webhook **já não é preciso** (Make só chama
`Meta leads to supabase` agora) e foi removido, junto com um nó HTTP legado
(`Meta: enviar template`, órfão, substituído há muito pelo `Send template`
nativo). Fica só `Execute Workflow Trigger` a alimentar `Ler lead no
Supabase`.

**Bug real apanhado ao testar** (não relacionado com nada mudado nesta
sessão, só nunca tinha sido exercitado): `Guardas`, condições 3
(`template_enviado_em` vazio) e 5 (`contacto_humano_em` vazio) usavam operador
`type: "object"` com `typeValidation: "strict"`. Funciona com `null`, **rebenta
com uma string não-vazia** — exactamente o valor de uma lead já contactada
(`"2026-09-07T12:41:53.453+00:00"`, timestamp em texto). Efeito em produção:
sempre que uma lead já contactada reentrasse aqui (webhook repetido), a
execução rebentava em vez de a guarda bloquear normalmente — falha silenciosa
em vez do skip esperado. Corrigido: `type: "string"` nas duas. Confirmado ao
vivo com `Raul Sampaio` (`1753122142635094`, `estado: contactada`) — antes
rebentava, depois bloqueou limpo.

## Outros fixes no `Meta leads to supabase`

- `DADOS - FB FORM` (ramo compra/arrendamento) lia campos de `$json` cru em
  vez de `$('Meta Lead Info').item.json` — o item que lhe chegava era o
  output do `Meta Form Name` (só `{name, id}`), não tinha `field_data`. Toda
  lead compra/arrendamento rebentava aqui, nunca testado antes (todos os
  testes manuais anteriores usavam sempre a mesma lead de Angariação).
- `Get many rows`/`If`/`No Operation`/`Create a row` (dedup nativo antigo do
  ramo venda): com 0 resultados o Supabase nativo devolve 0 items, e um nó
  sem items de entrada não corre — ou seja nenhuma lead nova (o caso comum)
  chegava a criar linha. Substituído por insert directo (depois por RPC).
  Nós antigos ficaram desligados no canvas, não apagados, para comparação.
- `apikey` da RPC de Angariação estava hardcoded no corpo do nó HTTP Request
  — movido para credencial `httpHeaderAuth` no cofre.
- `Meta Lead Info.node` ficou hardcoded a um ID de teste fixo depois de uma
  sessão de debug manual no editor — revertido para `={{ $json.body }}`.
- 409 de duplicado no insert directo (ramo venda, antes de virar RPC)
  rebentava a execução toda; `onError: continueRegularOutput` resolvia até a
  RPC (`lead_meta_compra`) tornar o problema moot (devolve 200 sempre).

## Scraper — logging do erro real

`scraper/app.py`: `except RuntimeError` no `/run/oportunidades-completo` ia
direito a `HTTPException` sem passar por `logger` — o erro real só existia no
corpo da resposta, que o `curl -sf` do cron suprime. Adicionado
`logger.error`. Deployado (commit `5caebef`).

## Por fazer

- Testar `lead_meta_recrutamento` ponta a ponta quando chegar a primeira lead
  real dessa campanha.
- Template WhatsApp de Recrutamento — por aprovar na Meta; sem ele não há
  fluxo de envio (só RPC + routing feitos).
- Decidir com o Miguel: separar `contactos.tipos` em origem/categoria (ideia
  do utilizador, não aplicada — mudança estrutural numa tabela partilhada).
- Migração maior, ainda sem plano: Matilde e Bárbara passarem a ler
  `contactos` em vez de `leads`/`leads_angariacao` (que desaparecem no
  futuro). Toca `engine.py`, `guards.py`, `assistants.py`, `router.py` — fase
  a sério, com plano próprio antes de código.
