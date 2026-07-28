# CLAUDE.md — Figueirahome Agent Call

> Contexto principal do projecto. Lido automaticamente em cada sessão.

---

## O que é

Plataforma de IA para agência imobiliária em Portugal:
1. **Agente de Voz** — atende clientes em todos os canais (voz, WhatsApp, web), recolhe dados, grava no Supabase.
2. **Assistente Broker** — chat interno com acesso à base de dados (uso exclusivo do corretor).
3. **Painel de gestão** — React web app para gerir clientes, imóveis, leads e agentes.

---

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | React + Tailwind v4 (Vite) → Cloudflare Pages |
| Backend | FastAPI (Python, async) → Fly.io |
| Base de dados | Supabase (PostgreSQL + Auth) — 2 projectos |
| Telefonia | Telnyx (Call Control + Media Streaming) |
| STT | OpenAI Whisper (PT) |
| IA | Claude API — Sonnet 4.6 (httpx directo, não SDK) |
| TTS | Telnyx `speak()` — voz `Polly.Ines-Neural` |

Backend **obrigatoriamente** em Fly.io — WebSockets persistentes para streaming de áudio.

---

## Estrutura

```
backend/app/
├── main.py          ← FastAPI + CORS + routers
├── config.py        ← pydantic-settings (SUPABASE_*, SUPABASE_IMOVEIS_*, EGOREALESTATE_*)
├── api/             ← clientes, imoveis, imoveis_sync, leads, tarefas, config, dashboard, broker
├── agents/
│   ├── voice/       ← webhook Telnyx, audio_ws, whatsapp_intake, save_call
│   └── broker/      ← tools, conversation, claude_agent, channels/whatsapp/
├── integrations/    ← egorealestate.py (cliente API), imoveis_sync.py (upsert)
├── db/supabase_client.py  ← get_supabase() [dados, projecto unificado] + get_supabase_auth() [só login]
└── models/          ← Pydantic (imovel, cliente, lead, tarefa, ...)

frontend/src/
├── App.jsx          ← React Router v6
├── components/      ← Layout, Sidebar (dark), ProtectedRoute
├── pages/           ← Dashboard, Clientes, Imoveis (abas: Portfólio/Tarefas/Sincronização), Leads, Agente1, Agente2, Config
└── lib/             ← supabase.js, api.js
```

---

## Estado actual — Handoff 2026-07-28

### Produção

| Componente | URL | Estado |
|---|---|---|
| Backend | `https://figueirahome-agentos.fly.dev` | ✅ deployado, secrets eGO API + CRM postos |
| Frontend | `https://figueirahome-agentos.pages.dev` | ✅ Cloudflare Pages, auto-deploy do push |
| WhatsApp | agente responde + pesquisa imóveis reais | ✅ end-to-end funcional |
| Cron sync eGO | `.github/workflows/sync-imoveis.yml` | ✅ diário, só **API** (CRM manual, ver Decisões) + `workflow_dispatch` |
| Git | `https://github.com/imogermano-dotcom/figueirahome_agentOS` | ✅ master, tudo pushed (último: `81addb2`) |

### Base de dados unificada (fases A–D2)

Todas as tabelas vivem no projecto Supabase secundário (`zphasvfopnbzwnaidsnw`, settings `supabase_imoveis_*`). Projecto original (`supabase_url/key`) fica **só Auth** (contas reais dos corretores). `get_supabase()` = dados; `get_supabase_auth()` = só valida login.

### Sincronismo eGO (fases B, F, G)

Duas acções separadas em `backend/app/integrations/imoveis_sync.py`: `sync_egorealestate_api()` (Web API pública, full pull paginado, corre no cron diário) e `sync_egorealestate_crm()` (CRM backoffice autenticado, única fonte com visibilidade total incl. não-publicados; retirado do cron — ver Decisões arquitecturais — corre só via botão "Validar CRM"). Coluna `publicado` (GENERATED STORED, migration `0008`) e `disponivel_na_api` (plain boolean) — detalhe da regra em Decisões arquitecturais.

### Fase 2 — scrapers de relatório eGO (Playwright)

Dois scripts novos, correm **só local** (Fly.io não tem RAM para Chromium — ver Decisões arquitecturais):
- `backend/scripts/export_relatorio_imoveis.py` — dispara relatório `jmarques_imoveis` (filtro "Disponível") no CRM eGO, faz download, faz parse e grava em `teste_imoveis`.
- `backend/scripts/export_relatorio_oportunidades.py` — dispara relatório `jmarques_oportunidades_notas` (filtro "Editado em > Últimas 48 horas", sem "Minhas oportunidades") e grava em `teste_oportunidades`.

Ambos reutilizam a sessão de login de `egorealestate_crm._login()` (cookies injectados no Playwright), aplicam filtros via `dispatchEvent` (não `.click()`), fundem múltiplas linhas de nota por entidade em `extra.notas[]`, e ignoram linhas do relatório sem referência. Testados com dados reais: 66 imóveis únicos / 19 oportunidades únicas.

Descoberta desta fase: existe uma tabela `oportunidades` de produção (~90 colunas, ~25k linhas) alimentada por um processo externo ao repo, nunca antes documentada — agora em `docs/database-schema.md`, **não gerida por este projecto**.

`teste_imoveis`/`teste_oportunidades` (migrations `0009`–`0011`) são staging (todas `text` + `extra jsonb`, mesmos nomes de coluna que o destino real) — dados ainda não promovidos para produção, decisão em aberto (ver Próximos passos).

### Ambiente local

- Python: `C:\Users\joaoa\AppData\Local\Programs\Python\Python312\python.exe`
- fly CLI: `C:\Users\joaoa\.fly\bin\flyctl.exe deploy --app figueirahome-agentos` (a partir de `backend/`)
- `backend/.env` — Supabase (ambos) ✅, Anthropic ✅, OpenAI ✅, eGO API + CRM ✅, Telnyx ❌, Meta ❌
- Scrapers Playwright: `pip install -r backend/scripts/requirements-scraper.txt` + `playwright install chromium`

### Bloqueadores activos

| Item | Estado |
|---|---|
| Credenciais Telnyx (3 vars) | ❌ bloqueia chamadas de voz |
| Número PT +351 Telnyx | ❌ requer regulatory requirement group |
| Número WhatsApp do corretor | ❌ bloqueia `escalar_para_broker` |
| ~3459 linhas `fonte='manual'`/`Em Prospecção` de origem desconhecida | ⚠️ investigação parada a pedido do utilizador — não mexer sem ser pedido de novo |

### Próximos passos

1. **Decidir promoção `teste_imoveis`/`teste_oportunidades` → produção** — ou manter só como consulta manual pontual. `teste_oportunidades` não deve substituir a `oportunidades` real sem confirmar com o utilizador (já tem processo próprio a alimentá-la).
2. **Reformulação Agentes + Dashboard** — pedido original antes de imóveis ter aberto esta sessão; ainda por planear.
3. **`escalar_para_broker`** — plano pronto (tool no WhatsApp, padrão de `pesquisar_imoveis`); falta só o número do corretor.
4. **Telnyx PT** — regulatory requirement, comprar +351, configurar secrets Fly.io.
5. Reavaliar se/quando voltar a incluir a validação CRM no cron diário.

---

## Decisões arquitecturais

- **Agente unificado**: `agente_config[agente='voz']` é a persona de atendimento ao cliente (voz, WhatsApp, web). `agente_config[agente='broker']` é exclusivo para uso interno do corretor.
- **Dois projectos Supabase, papéis divididos**: `get_supabase()` = todos os dados (projecto `zphasvfopnbzwnaidsnw`, dados unificados desde 2026-07-21); `get_supabase_auth()` = só validação de login (projecto original, onde vivem as contas reais). Backend usa sempre `service_role_key` para dados — nunca passa o JWT ao Postgres — por isso um token emitido pelo projecto de Auth valida-se normalmente mesmo com os dados noutro projecto (RLS nunca chega a ser avaliado). Lazy singletons em `db/supabase_client.py`.
- **Tool forcing WhatsApp**: quando user menciona critérios de pesquisa (regex `_SEARCH_RE`), `tool_choice: {"type":"tool","name":"pesquisar_imoveis"}` é forçado na iteração 0. Sem este mecanismo Claude ignorava as tools e prometia callbacks.
- **Prompt caching**: system prompt como lista com `cache_control: ephemeral` + beta header. Cache hits custam 10% do preço normal.
- **Aging de conversas**: `load_conversation` verifica `atualizado_em`; se > 48h retorna `None, []` e `save_conversation` cria nova linha.
- **Tailwind v4** via `@tailwindcss/vite` — sem `tailwind.config.js`
- **Auth backend**: `require_auth` FastAPI Depends por router; RLS activo (service_role_key no backend = bypass automático)
- **Supabase backend**: sync via `asyncio.run_in_executor()` (supabase-py é síncrono)
- **TTS** via `speak()` REST, não via WebSocket; **µ-law decode** manual (sem `audioop`, removido no Python 3.13)
- **Extracção de dados voz**: só no hangup (Claude tool use sobre transcrição completa)
- **CORS**: `frontend_url` + regex `*.figueirahome-agentos.pages.dev` para preview deploys
- **Sync eGO sempre full, nunca incremental**: `/v1/Properties/Latest?Since=` confirmado avariado (ignora `Since`, devolve sempre 1 imóvel) — não tentar reintroduzir cursor incremental nesta API sem reconfirmar que o eGO corrigiu o bug.
- **CRM backoffice como fonte de verdade de `disponibilidade`, mas não no cron automático**: Web API pública só vê publicados; o CRM autenticado (`egorealestate_crm.py`) é a única fonte com visibilidade total, usado para criar/corrigir linhas fora do alcance da API pública — mas por sobrepor às vezes um estado "Disponível" que a API pública já confirmava (dados desactualizados do lado do CRM), passou a correr só manual, não no cron diário.
- **"Sem acesso" no CRM ≠ permissão negada por defeito**: uma ficha que devolve "Você não pode consultar este imóvel" é, mais frequentemente, um `ego_id` desactualizado (imóvel recriado com novo ID) do que uma restrição real de permissão — `find_by_ref()` (campo `FreeText`, não `searchText`) resolve isto automaticamente antes de sinalizar tarefa.
- **`publicado` como coluna GENERATED, não campo escrito pela app**: critério de publicação no site é puramente função de outras colunas da mesma linha (`disponibilidade`, `imovel_ref`, preços, `disponivel_na_api`) — Postgres recalcula sempre, nunca dessincroniza. `disponivel_na_api` é a excepção (plain boolean): só a app sabe, a cada pull da API, se um ref ainda foi devolvido.
- **Scrapers de relatório eGO (Playwright) correm só local, nunca em Fly.io**: Chromium headless excede a RAM da VM Fly (256MB) — não criar botão no painel para isto sem rever o plano de hosting primeiro.
- **Staging antes de produção para dados de scraping**: qualquer nova fonte via scraping de relatório entra primeiro numa tabela `teste_*` (todas `text` + `extra jsonb`, mesmos nomes de coluna que o destino real) para inspeccionar valores crus antes de decidir tipos/transformações — nunca escrever directo em `imoveis`/`oportunidades` de produção durante a fase de teste.

## Bugs conhecidos

- **Sem barge-in**: utilizador não pode interromper agente de voz enquanto fala
- **Estado de sessão em memória**: sessões de voz perdidas em restart do servidor
- **Race condition voz**: `is_speaking` depende de `call.speak.ended` antes do próximo chunk
- **Janelas fixas de 2s**: sem VAD real; pode cortar frases longas

---

## Convenções

- **Python:** PEP 8, type hints, async.
- **React:** componentes funcionais + hooks. Sem class components.
- **Nomes:** código em inglês; UI em PT-PT.
- **DB:** tabelas e colunas em português, snake_case.
- **Segredos:** nunca hardcoded. Só em `.env` / Fly.io secrets.

---

## Regras para o Claude Code

1. Ler `docs/PRD.md` antes de feature nova.
2. Consultar `docs/database-schema.md` antes de tocar na DB.
3. Consultar `docs/api-spec.md` antes de criar/alterar endpoints.
4. **Fase nova → seguir `planeamento-fases.md`. Plano antes de código. Sempre.**
5. Uma fase de cada vez. Primeira resposta a fase nova = plano (nunca código directo).
6. Manter este ficheiro actualizado após cada fase. Limite: 200 linhas.
7. Nunca inventar credenciais.
