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

## Estado actual — Handoff 2026-07-21

### Produção

| Componente | URL | Estado |
|---|---|---|
| Backend | `https://figueirahome-agentos.fly.dev` | ✅ deployado, secrets eGO postos (`EGOREALESTATE_API_KEY`/`SYNC_SECRET`) |
| Frontend | `https://figueirahome-agentos.pages.dev` | ✅ Cloudflare Pages, auto-deploy do push, portal de imóveis live |
| WhatsApp | agente responde + pesquisa imóveis reais | ✅ end-to-end funcional, sem alterações nesta sessão |
| Cron sync eGO | `.github/workflows/sync-imoveis.yml` | ✅ testado manualmente (`workflow_dispatch`), GitHub Secret posto |
| Git | `https://github.com/imogermano-dotcom/figueirahome_agentOS` | ✅ master, tudo pushed (último: `e0c4657`) |

### Implementado (sessão 2026-07-21 — reformulação imóveis, fases A–E)

- **Base de dados unificada**: todas as tabelas (`imoveis`, `agente_clientes`, `agente_leads`, `agente_chamadas`, `agente_conversas`, `agente_config`, `agente_tarefas`) vivem agora no projecto Supabase secundário (`zphasvfopnbzwnaidsnw`, settings `supabase_imoveis_*`). O projecto original (`supabase_url/key`) fica **só como Auth** (10 contas reais de corretores — não dá pra migrar hashes de password via API) e como backup frio dos dados antigos. `get_supabase()` = dados (unificado); `get_supabase_auth()` = só valida login. Migrations `0004`, `0005` (obsoleta, ver nota no ficheiro), `0006`.
- **Tabela `imoveis` real** (não a aspiracional dos docs antigos): `imovel_ref` é a chave (sem uuid `id`), ~48 colunas incl. `ego_id`/`ego_atualizado_em`/`fotos`/`portais` já vindas de um import anterior do eGO. Só faltava `fonte` (migration `0004`).
- **Sync eGO Real Estate** — `backend/app/integrations/egorealestate.py` (cliente REST) + `imoveis_sync.py` (upsert por `imovel_ref`, cursor incremental = `max(ego_atualizado_em)`). Endpoint `POST /api/imoveis/sync/egorealestate` (JWT ou `X-Sync-Secret`). Cron diário `.github/workflows/sync-imoveis.yml`. **Validado em produção real** — mapeamento acertado contra a API viva (`BusinessName` vem em PT: "Venda"/"Arrendamento"; `Rooms`/`Floor` usam sentinela `INT32_MIN` p/ vazio; upsert por `imovel_ref`, não `ego_id`, por ser a PK real; dedup defensivo p/ referências duplicadas que o próprio eGO devolve).
- **Web scraper — SKIPPED conscientemente**: `figueirahome.com` é gerado pela própria eGO (redundante); `figueirahome.pt` real ainda não existe e vai ser alimentado pela nossa BD, não o contrário; Idealista/Imovirtual já syndicados via eGO. Necessidade real (imóveis não-publicados) exige CRM scraping autenticado — adiado, precisa de credenciais.
- **Tarefas** (`agente_tarefas`) — entidade genérica, CRUD em `backend/app/api/tarefas.py`, campo `imovel_ref` opcional (sem FK cross-projecto).
- **Portal `/imoveis`** — passou de listagem CRUD a 3 abas: Portfólio (campos reais), Tarefas, Sincronização (botão manual + resultado do último sync). Dashboard ganhou card "Tarefas pendentes".

### Tabelas activas

Projecto unificado (`supabase_imoveis_*`): `imoveis`, `agente_clientes`, `agente_leads`, `agente_chamadas`, `agente_conversas`, `agente_config`, `agente_tarefas`.
Projecto original (`supabase_url/key`): só Auth (10 contas) + tabelas antigas como backup frio, não usadas pelo backend.

### Ambiente local

- Python: `C:\Users\joaoa\AppData\Local\Programs\Python\Python312\python.exe`
- fly CLI: `C:\Users\joaoa\.fly\bin\flyctl.exe deploy --app figueirahome-agentos` (a partir de `backend/`) — **sem sessão activa nesta máquina, precisa `flyctl auth login` antes de correr secrets/deploy**
- Backend `localhost:8000` / Frontend `localhost:5173` — ambos testados e a funcionar nesta sessão
- `backend/.env` — Supabase (ambos os projectos) ✅, Anthropic ✅, OpenAI ✅, eGO Real Estate ✅ (key colada pelo utilizador), Telnyx ❌, Meta ❌

### Bloqueadores activos

| Item | Estado |
|---|---|
| Credenciais Telnyx (3 vars) | ❌ bloqueia chamadas de voz |
| Número PT +351 Telnyx | ❌ requer regulatory requirement group |
| Número WhatsApp do corretor | ❌ bloqueia `escalar_para_broker` |
| Credenciais CRM eGO (`EGOREALESTATE_CRM_*`) | ❌ bloqueia Fase F (validação automática de `disponibilidade`) — código pronto, falta colar no `.env`/Fly secrets |

### Próximos passos

1. **Reformulação Agentes + Dashboard** — era o pedido original antes de imóveis ter aberto esta sessão inteira; ainda por planear
2. **`escalar_para_broker`** — plano pronto (tool no WhatsApp, padrão de `pesquisar_imoveis`); falta só o número do corretor
3. **Fase F — validação automática via CRM eGO** — código feito (`egorealestate_crm.py` + `imoveis_sync.py::validar_disponibilidade_crm`, corre dentro do sync existente), falta só credenciais reais + teste local + deploy (secrets Fly + GitHub, mesmo padrão da API key)
4. **Telnyx PT** — regulatory requirement, comprar +351, configurar secrets Fly.io

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
