# Handoff — 2026-09-05

> Um imóvel retirado no eGO ficou "Disponível" na BD por atraso do cron —
> investigado, corrigido à mão e o cron reforçado. A seguir, rastreabilidade
> de quem dispara cada sync (cron vs painel) e uma limpeza da página de
> sincronização no painel. Continuação directa do handoff de 02/09.

## O que foi implementado

### 1. Diagnóstico do FH2571 — "Disponível" na BD, retirado no eGO

Pedido directo do utilizador para investigar. BD (`imoveis`) dizia
`disponibilidade=Disponível`, `publicado=true`, `disponivel_na_api=true`,
última alteração 06/08. A Web API pública do eGO (`GET /v1/Properties` e
`GET /v1/Properties/{ego_id}`) já devolvia **404** para o `ego_id`
26169502. O cron desse dia (`sync-imoveis.yml`, 10:43 UTC) tinha corrido
bem com `nao_publicados:0` — o imóvel saiu do eGO **depois** dessa
corrida, antes da investigação. Não era bug: `_flag_unpublished` +
`validar_disponibilidade_crm` (`imoveis_sync.py`) apanham isto sozinhos no
cron seguinte. Corrido sync manual (`X-Sync-Secret`) para corrigir já —
confirmado `disponibilidade=Retirado`, `publicado=false`.

### 2. Segunda corrida diária do cron de imóveis (`58144e0`)

Só 1 cron/dia (06:00 UTC) deixava até 24h de janela entre uma mudança no
eGO e o site reflecti-la — foi essa janela que escondeu o FH2571.
Adicionado `cron: "0 13 * * *"` a `.github/workflows/sync-imoveis.yml`.
Pedido explícito do utilizador; não tocado o cron de oportunidades
(03:00 UTC, afastado de propósito da app principal — ver `CLAUDE.md`).

### 3. `origem` (cron/manual) em `agente_sync_log` (`2995f47`)

Pedido do utilizador para se saber, por execução, se foi o cron ou um
clique no painel a disparar o sync. `require_sync_access` (`api/deps.py`)
já distinguia isto — devolve `"sync-secret"` quando autenticado por
`X-Sync-Secret` (cron), ou o utilizador do JWT (painel) — só faltava usar
o valor. Migration `0034_sync_log_origem.sql` (`alter table
agente_sync_log add column origem text`, corrida à mão pelo utilizador).
`_log_execucao` e `sync_egorealestate_api/crm` (`imoveis_sync.py`) e
`_log_execucao` (`api/oportunidades_sync.py`) ganham parâmetro `origem`,
os três endpoints calculam `"cron" if acesso == "sync-secret" else
"manual"` a partir do `Depends(require_sync_access)`. Painel mostra um
badge junto à "Última execução" e no histórico.

**Limitação por design, descoberta em produção**: `origem` reflecte
**como** o pedido autenticou, não literalmente "o GitHub Actions correu".
Um `curl` manual com `X-Sync-Secret` (feito para verificar o deploy) ficou
gravado como `"cron"` — correcto pela regra, mas confuso à primeira vista.
Fica uma linha de teste em produção (2026-09-04T17:29:55Z) mal-rotulada
por causa disto; tentativa de apagar bloqueada pelo classificador de
permissões, deixada por ser inofensiva.

### 4. Limpeza da página de sincronização no painel (`0da194f`, `b90bca9`)

Pedido do utilizador, duas iterações. `frontend/src/pages/Imoveis.jsx`,
`SincronizacaoTab` (imóveis) e `OportunidadesSyncCard` (oportunidades):

- Lista de imóveis alterados da última execução sai da vista inline,
  passa a botão **"Ver imóveis atualizados (N)"** que abre modal (reusa o
  `Modal` já existente no ficheiro — não há precedente de `window.open`
  no painel).
- "Execuções anteriores" mostra sempre só os últimos 2 dias
  (`DOIS_DIAS_MS`, filtro em `executado_em`).
- Botão **"Ver histórico completo"** busca `limit=500` ao endpoint de log
  e abre um modal fechável à parte — a vista principal nunca é substituída
  in-place (1ª versão fazia isso; corrigido a pedido do utilizador).
- Mesma lógica nos dois cartões (imóveis e oportunidades).

## Ficheiros principais modificados

- `.github/workflows/sync-imoveis.yml` — cron às 13:00 UTC.
- `supabase/migrations/0034_sync_log_origem.sql` — novo, coluna `origem`.
- `backend/app/integrations/imoveis_sync.py` — `_log_execucao`,
  `sync_egorealestate_api`, `sync_egorealestate_crm` ganham `origem`.
- `backend/app/api/imoveis_sync.py` — endpoints calculam `origem` a partir
  de `Depends(require_sync_access)`.
- `backend/app/api/oportunidades_sync.py` — idem.
- `backend/tests/test_imoveis_sync.py` — lambdas de `_log_execucao`
  actualizadas para o novo parâmetro.
- `frontend/src/pages/Imoveis.jsx` — `SincronizacaoTab`,
  `OportunidadesSyncCard` reescritos (modais de detalhe e histórico).
- Suite continua em **237** testes, todos a passar.

## Decisões arquitecturais

- **`origem` reaproveita a fronteira de auth que já existia**
  (`require_sync_access`) em vez de um header novo — cron e painel já
  autenticavam de formas distintas, só faltava gravar qual.
- **Histórico completo é sob pedido, não por omissão** — o painel só busca
  `limit=500` quando o botão é clicado; a vista por defeito fica barata
  (2 dias, `limit` pequeno já usado no `carregarLog` normal).
- **Modal, não nova janela do browser** — consistente com o resto do
  painel (`Clientes.jsx`, `Leads.jsx`, `Imoveis.jsx` já usam o mesmo
  padrão de `Modal`); sem precedente de `window.open` no código.

## Bugs conhecidos — mudanças

- **Novo, por design**: `origem="cron"` não distingue "o GitHub Actions
  correu" de "alguém usou `X-Sync-Secret` manualmente" — são a mesma
  fronteira de auth. Não corrigir sem um sinal adicional (ex: user-agent
  ou um segredo à parte só para a Action), o que não foi pedido.
- Os restantes (atraso de 12h do `01`, falta de `logging.basicConfig`,
  `agente_leads` morta, dedup de clientes sob carga, agente de voz)
  **inalterados** — ver `CLAUDE.md`.

## Próximos passos

Nenhum gerado por esta sessão além do já listado no `CLAUDE.md` (widget do
site, importar `02`/`03` do n8n, reenviar as 45 leads antes de 23/09,
varrer duplicados antigos). Um opcional, não pedido: apagar a linha de
teste `2026-09-04T17:29:55Z` em `agente_sync_log` quando o utilizador
quiser (bloqueado por permissões nesta sessão).
