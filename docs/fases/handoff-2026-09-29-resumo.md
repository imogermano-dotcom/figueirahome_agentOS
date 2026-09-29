# Handoff 2026-09-29

Continuação de 28/09 (Inês sem comissão, log erro WhatsApp, `pausa`). Hoje:
investigação tarefas eGO (scraper novo escrito, parado), atribuição de
anúncios Meta em `contactos` (fase completa, deployada), fixes de qualidade
de dados em `contactos`/`oportunidades` (telefone/telemovel, cliente_nome,
cliente_telefone/email), e backfill retroactivo de Setembro.

## Implementado

### 1. Atribuição Meta (`ad_id`/`ad_name`/`adset_id`/`adset_name`) — fase completa

Objectivo: analisar qualidade de leads por anúncio/conjunto de anúncios.
Plano formal (`docs/fases/contactos-atribuicao-ads-resumo.md`), fase nova.

- **Migration `0045_contactos_ad_attribution.sql`**: 4 colunas texto em
  `contactos`. Corrida pelo utilizador.
- **RPCs `lead_meta_compra/recrutamento/angariacao`**: +4 params
  `p_ad_id/p_ad_name/p_adset_id/p_adset_name` (default null), escritos em
  INSERT e UPDATE. Corridas pelo utilizador.
- **n8n `Meta leads to supabase` (`9DQlBhON12R1Pane`)**: 3 Set nodes +
  3 HTTP Request nodes actualizados para propagar os 4 campos (a Graph API
  já os pedia, só não iam para a frente). Validado 0 erros.
- **Backfill de leads de Recrutamento antigas**: workflow n8n dedicado
  (`oGTIZgsQmWmcW9Xy`, desactivado após uso) só serviu para buscar dados da
  Graph API — a escrita em `contactos` falhou por permissão da credencial
  (só RPC, sem UPDATE directo). Escrita final feita por mim via REST
  (`SUPABASE_SECRET_KEY`): 15 registos (12 + 3 encontrados a mais no
  reconto — discrepância 16 vs 12 vinha da fronteira horária do deploy do
  fix do `agente` de 25/09).

**Por confirmar**: fluxo ainda não testado com lead Meta nova a sério
(só com backfill de leads antigas).

### 2. Qualidade de dados em `contactos`/`oportunidades`

- **`telefone`/`telemovel` inconsistentes** — 3 escritores, 2 só gravavam
  uma coluna. Fix de escrita (`scraper/mapping_todas_colunas.py`,
  `guards._espelhar_em_contactos`) + fix de leitura
  (`guards.contacto_meta_aberto`, bug real: só via `telefone`, contacto
  só-scraper ficaria invisível ao routing). Detalhe:
  `docs/fases/telefone-telemovel-unificado-resumo.md`.
- **Backfill retroactivo de Setembro**: 61 `contactos` de 09/2026 só com
  uma das colunas — duplicado directo via REST (61/61 ok, 0 falhas,
  verificado sem sobras).
- **`oportunidades.cliente_telefone`/`cliente_email`** sempre `null` em
  quase tudo recente (14% preenchido vs 56% histórico) — pipeline actual
  nunca escrevia lá. Fix: espelha do `contactos` ligado (por nome) em
  `mapping_todas_colunas.py::group()`. Só aplica daqui para a frente +
  próxima corrida de scraper reprocessa o mês.
- **`oportunidades.cliente_nome` de Angariação** (achado 26/09) — fix já
  deployado; hoje só o caso pontual `CAP_22228` ("José") corrigido por
  pedido directo, não o histórico completo (~4233 linhas, fora de âmbito).

### 3. Tarefas do eGO — scraper escrito, NÃO ligado

Relatório "Oportunidades" nunca traz tarefas pendentes (só tarefas
*concluídas*, disfarçadas de nota) — confirmado com 3 configurações de
relatório diferentes. Existe um relatório eGO separado ("tarefas todas")
que traz tarefas pendentes com colunas próprias — `scraper/tarefas.py`
escrito e auto-testado contra `docs/tarefas todas_6429.xlsx` (28 linhas →
16 válidas). **Não ligado**: falta saber os passos de navegação do eGO até
essa página/relatório. Parado a pedido do utilizador.

### 4. Inês (A3) sem falar em comissão/ordenado variável

Ajuste de prompt — remete sempre para a entrevista com o responsável de
recrutamento, mantém as perguntas de qualificação normais.

## Ficheiros principais

- `scraper/tarefas.py` (novo, não ligado) · `scraper/oportunidades_completo.py`
  (`_trigger_and_download` aceita `report_name`)
- `scraper/mapping_todas_colunas.py` (`classify` espelha telefone→telemovel;
  `group` espelha cliente_telefone/cliente_email do contacto ligado)
- `backend/app/agents/broker/guards.py` (`contacto_meta_aberto` procura
  telefone OU telemovel; `_espelhar_em_contactos` grava as duas colunas)
- `supabase/migrations/0045_contactos_ad_attribution.sql`
- RPCs `lead_meta_compra/recrutamento/angariacao` (correu o utilizador)
- n8n `9DQlBhON12R1Pane` (Set + HTTP Request nodes)
- Testes: `test_guards.py`, `test_espelhar_contactos.py`,
  `mapping_todas_colunas.py::demo()` — suite 281 (extendida, não crescida)

## Decisões

- Backfills retroactivos ficam **sempre âmbito estreito** (mês corrente ou
  caso pontual pedido) — histórico completo é decisão à parte, não tomada
  aqui de ânimo leve.
- Correcção de dados via REST directo (não SQL) quando é escrita de **linha**
  (não schema/RPC) e o volume é pequeno (dezenas) — mais rápido, mesmo
  acesso de sempre (`SUPABASE_SECRET_KEY`).
- Fase Meta ads: só `contactos`, nunca `leads` — pedido explícito do
  utilizador, mesmo padrão de "assistentes nunca escrevem em `oportunidades`".

## Bugs conhecidos (novos/confirmados hoje)

- `guards.contacto_meta_aberto` só olhava a `telefone` — corrigido, não
  tinha ainda causado incidente ao vivo.
- Relatório Oportunidades do eGO não traz tarefas pendentes, por nenhuma
  configuração de relatório — não é bug nosso, é o motor de relatórios eGO.
- `_JANELA_LEAD_DIAS = 30` continua sem alteração (ver `lead-pausa-resumo.md`).

## Próximos passos

1. Tarefas eGO: obter passos de navegação da página "tarefas todas" do
   utilizador para ligar `scraper/tarefas.py`.
2. Testar fluxo de atribuição Meta com lead nova a sério (não backfill).
3. Retomar limpeza de duplicados em `contactos` — a auditoria de hoje
   (fill-rate de email/telefone) era o pré-requisito pedido pelo utilizador;
   ainda não iniciada.
4. Decidir se `cliente_telefone`/`cliente_email`/`cliente_nome` justificam
   backfill histórico completo (~4233 linhas) ou ficam só daqui para a
   frente.
