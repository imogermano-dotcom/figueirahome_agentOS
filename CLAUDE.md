# CLAUDE.md — Figueirahome Agent Call

> Contexto principal do projecto. Lido automaticamente em cada sessão.

---

## O que é

Plataforma de IA para agência imobiliária em Portugal:
1. **Agente de Voz** — atende chamadas, recolhe dados, grava no Supabase.
2. **Assistente Broker** — chat com acesso à base de dados (web, WhatsApp).
3. **Painel de gestão** — React web app para gerir clientes, imóveis, leads e agentes.

---

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | React + Tailwind v4 (Vite) → Vercel |
| Backend | FastAPI (Python, async) → Fly.io |
| Base de dados | Supabase (PostgreSQL + Auth) |
| Telefonia | Telnyx (Call Control + Media Streaming) |
| STT | OpenAI Whisper (PT) |
| IA | Claude API — Sonnet (API directa, não SDK) |
| TTS | Telnyx `speak()` — voz `Polly.Ines-Neural` |

Backend **obrigatoriamente** em Fly.io — WebSockets persistentes para streaming de áudio.

---

## Estrutura

```
backend/app/
├── main.py                        ← FastAPI v0.4.0 + CORS + todos os routers
├── config.py                      ← pydantic-settings (Supabase, Anthropic, OpenAI, Telnyx, Meta)
├── api/
│   ├── deps.py                    ← require_auth (Supabase JWT via Depends)
│   ├── clientes.py                ← CRUD /api/clientes
│   ├── imoveis.py                 ← CRUD /api/imoveis + POST /api/imoveis/import (CSV)
│   ├── leads.py                   ← CRUD /api/leads (join agente_clientes)
│   ├── config.py                  ← GET/PUT /api/config/{agente}
│   ├── dashboard.py               ← GET /api/dashboard (métricas)
│   └── broker.py                  ← POST /api/broker/chat
├── agents/
│   ├── voice/                     ← Agente de Voz (Fase 2)
│   │   ├── whatsapp_intake.py     ← reconhecimento cliente existente por telefone
│   │   └── ...
│   └── broker/                    ← Agente Broker (Fase 3a)
│       ├── tools.py               ← consultar_clientes/imoveis/leads
│       ├── conversation.py        ← histórico em agente_conversas
│       ├── claude_agent.py        ← get_response() com tool calling
│       └── channels/whatsapp/     ← meta_api.py + webhook.py
├── db/supabase_client.py
└── models/                        ← Pydantic (6 entidades)

frontend/src/
├── App.jsx                        ← React Router v6
├── components/                    ← Layout (zinc-950 bg), Sidebar (dark), ProtectedRoute
├── pages/                         ← Dashboard, Clientes, Imoveis, Leads, Agente1, Agente2, Config
└── lib/                           ← supabase.js, api.js
```

---

## Estado actual — Handoff 2026-06-15

### Fases concluídas

**Fase 1 ✅** — Fundação: FastAPI base, frontend auth Supabase, routing, layout

**Fase 2 ✅** — Agente de Voz (código completo, bloqueado por credenciais Telnyx)
- Pipeline completo: webhook Telnyx → WebSocket áudio → STT → Claude → TTS
- `save_call.py` — Claude tool use + Supabase upsert — ✅ testado e validado

**Fase 3a ✅** — Broker + WhatsApp + Reconhecimento de Clientes
- `POST /api/broker/chat` — chat web com Claude + tool calling DB
- `GET/POST /webhook/whatsapp` — verificação + receber/responder mensagens
- `whatsapp_intake.py` — lookup DB por telefone → prompt dinâmico (novo vs. existente)
  - Cliente existente: injeta perfil, não re-pergunta dados já conhecidos
- Histórico em `agente_conversas`, assinatura X-Hub-Signature-256 verificada

**Fase 4a ✅** — Backend CRUD completo
- `api/deps.py` — `require_auth` valida JWT Supabase em todos os `/api/*`
- `api/clientes.py` — CRUD + filtros (search, tipo, zona, origem)
- `api/imoveis.py` — CRUD + import CSV (preco/area float, quartos int)
- `api/leads.py` — CRUD + join `agente_clientes(nome, telefone)`
- `api/config.py` — GET/PUT por agente (voz|broker)
- `api/dashboard.py` — chamadas_hoje, leads_novos, imoveis_disponiveis, conversas_hoje

**Fase 4b ✅** — Frontend dark mode completo
- Todas as páginas funcionais (sem stubs): Dashboard, Clientes, Imóveis, Leads, Agente1, Agente2, Config
- Tema: zinc-950 bg, zinc-900 surfaces, zinc-800 inputs, gradientes blue→violet
- Dashboard: 4 cards gradiente com blobs coloridos, números em gradiente
- Agente2: chat UI com typing dots animados
- Config: lista de status de credenciais (verde/vermelho por env var)

**Fase 4c ✅** — RLS Supabase activo
- `supabase/migrations/0003_rls.sql` — RLS habilitado em todas as 6 tabelas `agente_*`
- Política `auth_full_access` para `authenticated` em cada tabela
- `anon` bloqueado por defeito; `service_role` (backend) bypassa automaticamente
- Aplicar migration no Supabase dashboard (SQL Editor)

### Tabelas activas (prefixo `agente_`)

`agente_clientes`, `agente_imoveis`, `agente_leads`, `agente_chamadas`, `agente_conversas`, `agente_config`

Migration `0001` não aplicada ao remoto (marcada via `migration repair`). Não reaplicar.

### Ambiente local

- Python: `C:\Users\joaoa\AppData\Local\Programs\Python\Python312\python.exe`
- Backend v0.4.0: `localhost:8000` — arrancar com `Start-Process -WindowStyle Hidden`
- Frontend: `localhost:5173` (Vite dev server)
- `backend/.env` — Supabase ✅, Anthropic ✅, OpenAI ✅, Telnyx ❌, Meta ❌

### Bloqueadores activos

| Item | Estado |
|---|---|
| Credenciais Telnyx (3 vars) | ❌ — bloqueia chamadas de voz |
| Número PT +351 Telnyx | ❌ — requer regulatory requirement group |
| Credenciais Meta (4 vars) | ❌ — bloqueia WhatsApp real |
| ngrok URL muda no arranque | ⚠️ — atualizar webhook Meta manualmente |

### Próximos passos

1. **Deploy Fly.io** — mover de local+ngrok para produção
2. **WhatsApp real** — criar Meta App, configurar WABA, preencher vars
3. **Telnyx PT** — preencher regulatory requirement, comprar +351

---

## Decisões arquitecturais

- **Tailwind v4** via `@tailwindcss/vite` — sem `tailwind.config.js`
- **Supabase URL** frontend: sem `/rest/v1/` no fim
- **Auth backend**: `require_auth` FastAPI Depends por router; RLS activar na Fase 4c
- **Supabase backend**: sync via `asyncio.run_in_executor()` (supabase-py é síncrono)
- **Reconhecimento cliente WhatsApp**: lookup por telefone antes de Claude; prompt split novo/existente
- **TTS** via `speak()` REST, não via WebSocket
- **µ-law decode** manual — sem `audioop` (removido no Python 3.13)
- **Extracção de dados voz**: só no hangup (Claude tool use sobre transcrição completa)
- **Webhook signature Telnyx**: verificada em `production`, ignorada em `development`

## Bugs conhecidos / limitações

- **Sem barge-in**: utilizador não pode interromper agente de voz enquanto fala
- **Estado de sessão em memória**: sessões perdidas em restart do servidor
- **Race condition voz**: `is_speaking` depende de `call.speak.ended` antes do próximo chunk
- **Janelas fixas de 2s**: sem VAD real; pode cortar frases longas

---

## Convenções

- **Python:** PEP 8, type hints, async.
- **React:** componentes funcionais + hooks. Sem class components.
- **Nomes:** código em inglês; UI em PT-PT.
- **DB:** tabelas e colunas em português, snake_case.
- **Segredos:** nunca hardcoded. Só em `.env`. Placeholders em `.env.example`.

---

## Regras para o Claude Code

1. Ler `docs/PRD.md` antes de feature nova.
2. Consultar `docs/database-schema.md` antes de tocar na DB.
3. Consultar `docs/api-spec.md` antes de criar/alterar endpoints.
4. **Fase nova → seguir `planeamento-fases.md`. Plano antes de código. Sempre.**
5. Uma fase de cada vez. Primeira resposta a fase nova = plano (nunca código directo).
6. Manter este ficheiro actualizado após cada fase.
7. Nunca inventar credenciais.
