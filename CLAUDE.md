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
├── config.py        ← pydantic-settings (inclui SUPABASE_IMOVEIS_*)
├── api/             ← clientes, imoveis, leads, config, dashboard, broker
├── agents/
│   ├── voice/       ← webhook Telnyx, audio_ws, whatsapp_intake, save_call
│   └── broker/      ← tools, conversation, claude_agent, channels/whatsapp/
├── db/supabase_client.py  ← get_supabase() + get_supabase_imoveis()
└── models/          ← Pydantic (6 entidades)

frontend/src/
├── App.jsx          ← React Router v6
├── components/      ← Layout, Sidebar (dark), ProtectedRoute
├── pages/           ← Dashboard, Clientes, Imoveis, Leads, Agente1, Agente2, Config
└── lib/             ← supabase.js, api.js
```

---

## Estado actual — Handoff 2026-07-08

### Produção ✅

| Componente | URL | Estado |
|---|---|---|
| Backend | `https://figueirahome-agentos.fly.dev` | ✅ Fly.io `ams`, auto-stop |
| Frontend | `https://figueirahome-agentos.pages.dev` | ✅ Cloudflare Pages |
| WhatsApp | agente responde + pesquisa imóveis reais | ✅ end-to-end funcional |
| Login portal | imagem de fundo `marina_por_do_sol.jpg` | ✅ corrigido (ficheiro estava untracked, nunca tinha sido deployado) |
| Git | `https://github.com/imogermano-dotcom/figueirahome_agentOS` | ✅ master |

### Implementado (cumulativo)

- **Pesquisa imóveis WhatsApp** — tool `pesquisar_imoveis` em `whatsapp_intake.py`; liga ao 2.º Supabase (`zphasvfopnbzwnaidsnw`, tabela `imoveis`); keyword regex + `tool_choice` forçado garantem que Claude chama a tool em vez de prometer callback
- **Dedup de leads** — `_save_to_db` verifica lead activo (`estado not in [fechado, perdido]`) antes de inserir
- **Aging de conversas** — `conversation.py`: nova thread após 48h de inactividade (`_CONVERSATION_TTL_HOURS = 48`)
- **Prompt caching** — system prompt enviado como lista com `cache_control: ephemeral`; header `anthropic-beta: prompt-caching-2024-07-31`
- **Login portal** — imagem de fundo commitada e no ar (estava a faltar em produção por nunca ter sido versionada)

### Planeado, não implementado

- **`escalar_para_broker`** — tool no agente WhatsApp (`whatsapp_intake.py`), a seguir o padrão de `pesquisar_imoveis`/`guardar_dados_cliente`:
  - Nova tool schema em `_SAVE_TOOL`; handler faz update de `agente_leads.estado = "aguarda_broker"` (valor novo, coluna já é `text` livre — sem migration) e chama `send_text_message` (já existe em `agents/broker/channels/whatsapp/meta_api.py`) para o número do corretor
  - Novo setting `broker_whatsapp_number` em `config.py`
  - **Bloqueador:** falta número WhatsApp do corretor para o secret `BROKER_WHATSAPP_NUMBER` (Fly.io)

### Tabelas activas

`agente_clientes`, `agente_imoveis`, `agente_leads`, `agente_chamadas`, `agente_conversas`, `agente_config`

> Migration `0001` marcada via `migration repair` — **não reaplicar**.

### Ambiente local

- Python: `C:\Users\joaoa\AppData\Local\Programs\Python\Python312\python.exe`
- fly CLI: `C:\Users\joaoa\.fly\bin\flyctl.exe deploy --app figueirahome-agentos` (a partir de `backend/`)
- Backend: `localhost:8000` | Frontend: `localhost:5173`
- `backend/.env` — Supabase ✅, Anthropic ✅, OpenAI ✅, Telnyx ❌, Meta ❌ (local)

### Bloqueadores activos

| Item | Estado |
|---|---|
| Credenciais Telnyx (3 vars) | ❌ bloqueia chamadas de voz |
| Número PT +351 Telnyx | ❌ requer regulatory requirement group |
| Número WhatsApp do corretor | ❌ bloqueia implementação de `escalar_para_broker` |

### Próximos passos

1. **`escalar_para_broker`** — plano pronto (ver acima); falta só o número do corretor para codificar
2. **Formatação imóveis** — emojis e markdown WhatsApp na resposta do agente
3. **Telnyx PT** — preencher regulatory requirement, comprar +351, configurar secrets Fly.io

---

## Decisões arquitecturais

- **Agente unificado**: `agente_config[agente='voz']` é a persona de atendimento ao cliente (voz, WhatsApp, web). `agente_config[agente='broker']` é exclusivo para uso interno do corretor.
- **Dois clientes Supabase**: `get_supabase()` para CRM/agente; `get_supabase_imoveis()` para portefólio (`zphasvfopnbzwnaidsnw`). Lazy singletons em `db/supabase_client.py`.
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
