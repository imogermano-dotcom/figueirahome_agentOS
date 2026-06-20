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
| Base de dados | Supabase (PostgreSQL + Auth) |
| Telefonia | Telnyx (Call Control + Media Streaming) |
| STT | OpenAI Whisper (PT) |
| IA | Claude API — Sonnet 4.6 (httpx directo, não SDK) |
| TTS | Telnyx `speak()` — voz `Polly.Ines-Neural` |

Backend **obrigatoriamente** em Fly.io — WebSockets persistentes para streaming de áudio.

---

## Estrutura

```
backend/app/
├── main.py          ← FastAPI v0.4.0 + CORS + routers
├── config.py        ← pydantic-settings
├── api/             ← clientes, imoveis, leads, config, dashboard, broker (CRUD + auth)
├── agents/
│   ├── voice/       ← webhook Telnyx, audio_ws, whatsapp_intake, save_call
│   └── broker/      ← tools, conversation, claude_agent, channels/whatsapp/
├── db/supabase_client.py
└── models/          ← Pydantic (6 entidades)

frontend/src/
├── App.jsx          ← React Router v6
├── components/      ← Layout, Sidebar (dark), ProtectedRoute
├── pages/           ← Dashboard, Clientes, Imoveis, Leads, Agente1, Agente2, Config
└── lib/             ← supabase.js, api.js
```

---

## Estado actual — Handoff 2026-06-20

### Tudo em produção ✅

| Componente | URL | Estado |
|---|---|---|
| Backend | `https://figueirahome-agentos.fly.dev` | ✅ Fly.io `ams`, auto-stop |
| Frontend | `https://figueirahome-agentos.pages.dev` | ✅ Cloudflare Pages |
| WhatsApp | webhook verificado + agente a responder | ✅ end-to-end funcional |
| Git | `https://github.com/imogermano-dotcom/figueirahome_agentOS` | ✅ master actualizado |

### Fases concluídas

- **Fase 1** — Fundação: FastAPI, auth Supabase, routing, layout
- **Fase 2** — Agente de Voz: pipeline Telnyx → STT → Claude → TTS (código completo; bloqueado por credenciais)
- **Fase 3a** — WhatsApp: webhook Meta, `whatsapp_intake.py`, histórico `agente_conversas`
- **Fase 4a** — Backend CRUD: clientes, imóveis, leads, config, dashboard, `require_auth`
- **Fase 4b** — Frontend dark mode: todas as páginas funcionais, tema zinc-950
- **Fase 4c** — RLS Supabase: 6 tabelas `agente_*`, política `auth_full_access`
- **Deploy** — Fly.io + Cloudflare Pages + CORS preview deploys + secrets configurados

### Tabelas activas

`agente_clientes`, `agente_imoveis`, `agente_leads`, `agente_chamadas`, `agente_conversas`, `agente_config`

> Migration `0001` marcada via `migration repair` — **não reaplicar**.

### Ambiente local

- Python: `C:\Users\joaoa\AppData\Local\Programs\Python\Python312\python.exe`
- Backend: `localhost:8000` — arrancar com `Start-Process -WindowStyle Hidden`
- Frontend: `localhost:5173` (Vite)
- `backend/.env` — Supabase ✅, Anthropic ✅, OpenAI ✅, Telnyx ❌, Meta ❌ (local)

### Bloqueadores activos

| Item | Estado |
|---|---|
| Credenciais Telnyx (3 vars) | ❌ bloqueia chamadas de voz |
| Número PT +351 Telnyx | ❌ requer regulatory requirement group |

> Meta/WhatsApp: credenciais no Fly.io ✅, WABA configurado ✅, a funcionar em produção.

### Próximos passos

1. **Telnyx PT** — preencher regulatory requirement, comprar +351, configurar secrets Fly.io

---

## Decisões arquitecturais

- **Agente unificado**: `agente_config[agente='voz']` é a persona de atendimento ao cliente em todos os canais (voz, WhatsApp, web). `agente_config[agente='broker']` é exclusivo para uso interno do corretor.
- **Tailwind v4** via `@tailwindcss/vite` — sem `tailwind.config.js`
- **Supabase URL** frontend: sem `/rest/v1/` no fim
- **Auth backend**: `require_auth` FastAPI Depends por router; RLS activo
- **Supabase backend**: sync via `asyncio.run_in_executor()` (supabase-py é síncrono)
- **Reconhecimento cliente WhatsApp**: lookup por telefone antes de Claude; prompt split novo/existente
- **TTS** via `speak()` REST, não via WebSocket
- **µ-law decode** manual — sem `audioop` (removido no Python 3.13)
- **Extracção de dados voz**: só no hangup (Claude tool use sobre transcrição completa)
- **Webhook signature Telnyx**: verificada em `production`, ignorada em `development`
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
