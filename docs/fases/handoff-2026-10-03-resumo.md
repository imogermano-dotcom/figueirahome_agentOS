# Handoff 2026-10-03 — resumo

> Continuação do handoff de 29/09 (`handoff-2026-09-29-resumo.md`). Sessão de 29/09 a 03/10.
> Três linhas de trabalho: **Inês (A3)** corrigida, **tarefas do eGO** sincronizadas por cron, e
> **`contacto_id`** para relacionar as tabelas pelo ID do contacto.

## 1. O que foi implementado

### 1.1 `contacto_id` — relacionar as tabelas por ID do contacto (01/10)
**Problema:** `oportunidades`, `notas`, `tarefas`, `visitas` só tinham o nome do cliente; por nome é
ambíguo em 17 268 das 26 049 oportunidades.
- Migration **`0046`** (aplicada à mão): `contacto_id uuid` (FK `public.contactos(id)`, nullable,
  `ON DELETE SET NULL`) nas 4 tabelas + `contacto_match` em `oportunidades` (`ego_link|telefone|email|nome`).
  Duas RPCs, só `service_role`: `set_contacto_oportunidades(pares jsonb)` e `propagar_contacto_id()`.
- Scraper: `mapping_todas_colunas.group()` devolve `contacto_por_oportunidade` (o contacto com
  nome == `cliente_nome`); `upsert.run()` grava **`contactos` primeiro**, lê `ego_link → id` e chama a
  RPC (`_ligar_contactos`); `tarefas.py` chama `propagar_contacto_id()` no fim. Tudo best-effort.
- Resultado a 03/10: **46/26 058 oportunidades ligadas** (`ego_link`, 100% do relatório diário; 31/31
  conferidas por nome), 257 tarefas, 630 notas, 3 visitas — cresce com as edições.
- **Por correr:** backfill do histórico `docs/fases/contacto-id-backfill.sql` (telefone > email > nome;
  medido: 82% resolvíveis, 48% de alta confiança). Plano: `contacto-id-plano.md`.

### 1.2 Sync das tarefas activas do eGO (30/09)
`scraper/tarefas.py sync`: o relatório "tarefas todas" (`/egocore/tasks`) traz as 2192 activas mas o
eGO só dá download directo até ~1000, por isso fatia por data de criação (4 fatias: 5/520/801/866,
pesquisa avançada da página + contagem por `eventsearch`), faz upsert em `tarefas` e **fecha**
(`pendente → concluida`) as nossas que já não estão activas. 1.ª execução: +363 inseridas, 321 fechadas.
- Cron **`sync-tarefas`** `7 5 * * *` UTC (Cron Manager, job 6) → `POST /api/oportunidades/sync/tarefas`
  (backend, `X-Sync-Secret`, log `agente_sync_log tipo=egorealestate_tarefas`) → `POST /run/tarefas`
  (scraper). ~135 s. **Correu sozinho 01, 02 e 03/10.** Plano/limites: `tarefas-sync-plano.md`.

### 1.3 Inês (A3), 29/09 — deploy v106
- Recebe o contexto da candidatura Meta (`engine._contexto_recrutamento`: nome e template de
  `contactos`): deixou de perguntar o nome que o template já usava e de se apresentar duas vezes.
- Resposta sem texto depois das tools já não vira "Ocorreu um erro. Tenta novamente." — chamada final
  com `tool_choice: none`; fica `erro=sem_texto` em `agente_interacoes`.
- Lead de recrutamento nasce `tipo='recrutamento'` e `guards.agente_de_lead` devolve-a à Inês (com
  `compra` a thread expirada ia parar à Matilde). Prompt: não pede telefone no WhatsApp, não promete
  prazos, não volta a chamar tools depois de escalar. 2 duplicados de `contactos` apagados.

### 1.4 Outros (29/09)
- **Atribuição Meta ads** (`ad_id`/`ad_name`/`adset_*`, `0045`) testada com lead real: contacto antigo do
  eGO actualizado no sítio, sem duplicar.
- `telefone`/`telemovel` unificados em `contactos`; `oportunidades.cliente_telefone/email` espelhados do
  contacto ligado.

## 2. Ficheiros principais
| Área | Ficheiros |
|---|---|
| `contacto_id` | `supabase/migrations/0046_contacto_id.sql` · `docs/fases/contacto-id-{plano.md,backfill.sql}` · `scraper/{mapping_todas_colunas,upsert,tarefas}.py` |
| Tarefas | `scraper/tarefas.py` · `scraper/oportunidades_completo.py` (`_trigger_and_download` aceita `page_path` e `preparar`) · `scraper/app.py` (`/run/tarefas`) · `backend/app/api/oportunidades_sync.py` (`/oportunidades/sync/tarefas`) · `crons/schedules.json` |
| Inês | `backend/app/agents/broker/{engine,guards,tools,assistants}.py` |
| Docs | `docs/fases/{tarefas-sync-plano,contacto-id-plano,handoff-2026-10-03-resumo}.md` · `docs/fases/cron-manager-fly-resumo.md` |

Commits: `b355579` (Inês) · `4ab2d25` (docs/.gitignore) · `0a9f2dc` (tarefas) · `f4955e1` (cron) ·
`08c631a` + `a6ce909` (`contacto_id`, **por enviar para o remoto**).
Deploys: backend (v106 + endpoint tarefas), scraper (com `contacto_id`), crons (job 6).

## 3. Decisões arquitecturais
- **`oportunidades.contacto_id` é a fonte de verdade; `tarefas`/`notas`/`visitas` herdam-no** por
  `oportunidade_ref` (denormalizado para juntar directamente). Escrita **só por RPC**, nunca no upsert em
  lote: uma chave presente só em alguns registos escreve NULL nos outros (armadilha já conhecida do
  PostgREST) e apagaria o backfill.
- **FK para `contactos(id)`, não para a PK `(nome, criado_em)`**: o scraper grava `criado_em` com a data de
  alteração, por isso a PK muda a cada edição (foi o que partiu a FK de `leads_angariacao`).
- **Linha canónica = a que tem `ego_link`** (identidade real do eGO). A mesma pessoa tem 2+ linhas em
  `contactos`; fundir duplicados fica para a fase seguinte.
- **Histórico: daqui para a frente + heurística SQL** (sem backfill completo pelo eGO). **Avançou-se sem
  consultar o Miguel**; mitigação: colunas nullable, `IF NOT EXISTS`, inspecção prévia de triggers.
- **Sync de tarefas = snapshot completo em fatias**, não "últimos N dias": não há filtro de "editada em"
  nem de "concluída em", por isso só um snapshot das activas permite fechar as que saíram.
- **Vocabulário da tabela manda**: `pendente`/`concluida` e `origem_lista='todas_as_colunas'`.
- **Cron às 05:07 UTC** (06:07 Lisboa no verão): 70 min antes do `sync-imoveis` para não partilhar a
  sessão do eGO (sessões concorrentes já derrubaram a app).

## 4. Bugs conhecidos e riscos
- **Backfill de `contacto_id` por correr**: até lá só ~0,2% das oportunidades têm elo.
- **Camada "nome" do backfill (~33%) é de baixa confiança** (homónimos): `contacto_match='nome'`,
  desfazível; não usar para acções automáticas.
- **`contactos` duplicado**: 15 852 linhas sem `ego_link` (pipeline do Miguel) repetem ~10 000 das 12 631
  com `ego_link`. Duas tabelas `contactos` (`public` e `prospeccao`): qualificar sempre `public.`.
- **~10 oportunidades por sync ficam sem contacto** (colisão `(nome, criado_em)` no upsert de `contactos`).
- **`notas` dispara IA em cada INSERT** (`tgr_classify_lead`/`tgr_extract_prefs` → edge functions via
  `net.http_post`, pipeline do Miguel): custo proporcional às notas novas por sync. Não alterado.
- **`oportunidades` tem `BEFORE UPDATE` que carimba `atualizado_em`**: o backfill desliga-o durante os
  updates (se falhar a meio: `alter table oportunidades enable trigger trg_oportunidades_updated;`).
- **Tarefas apagadas/reagendadas no eGO** também fecham a linha antiga (reagendar muda `tarefa_due_raw`,
  parte da chave). Das 2192 activas, ~65 não têm `Referência` (tarefas internas) e 2 têm uma oportunidade ausente de `oportunidades` (FK): ficam de fora.
- **A4 (Bárbara) tem o mesmo buraco de contexto que a Inês tinha** (não recebe nada de `contactos`).
- **O `01` do n8n dispara ~12h tarde** (compra/arrendamento) — por investigar (o MCP do n8n não ligou).
- Uma lead de recrutamento antiga ficou em `leads.tipo='compra'` (a tabela `leads` de recrutamento foi
  ignorada por decisão: o que interessa é `contactos`).

## 5. Próximos passos
1. **Correr o backfill** `docs/fases/contacto-id-backfill.sql` (passos 1-4, olhar a amostra do passo 3;
   fora dos syncs 03:37 e 05:07 UTC). 24 h depois: `COUNT(contacto_id)` não desce.
2. `git push` dos commits `08c631a` e `a6ce909` (repo público; o diff não tem dados de clientes).
3. Dar à Bárbara (A4) o contexto de `contactos` (copiar `_contexto_recrutamento`, `tipo_contacto='vendedor'`).
4. Fundir duplicados em `contactos` e repontar `contacto_id` para a linha canónica (com o Miguel).
5. `contacto_id` em `leads`/`leads_angariacao`/`agente_clientes` (2.ª fase; retirar a FK composta).
6. Investigar o `01` do n8n a disparar tarde.
7. Actualizar `docs/database-schema.md` (um projecto; colunas de `contactos` e da `0046`).

## 6. Como verificar
- `sync-tarefas`: `agente_sync_log` com `tipo=egorealestate_tarefas`, `origem=cron` (05:09 UTC).
- `contacto_id`: `select contacto_match, count(*) from oportunidades group by 1;` e
  `select t.tarefa_titulo, c.nome from tarefas t join public.contactos c on c.id = t.contacto_id limit 20;`
- Testes: `pytest backend/tests/` (283); `python upsert.py`, `python mapping_todas_colunas.py`,
  `python tarefas.py` de `scraper/`; `python tarefas.py sync --dry` (descarrega, não escreve).
