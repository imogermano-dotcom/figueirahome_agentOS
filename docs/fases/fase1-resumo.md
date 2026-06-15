# Fase 1 — Resumo

**Data:** 2026-05-29  
**Estado:** Concluída

## O que ficou feito

- **Estrutura de pastas** completa conforme `CLAUDE.md` (backend, frontend, supabase/migrations, docs/fases)
- **Migration SQL** `supabase/migrations/0001_initial_schema.sql` — 6 tabelas, índices, dados iniciais de config
- **Backend FastAPI:**
  - `app/main.py` — servidor com CORS e `GET /health`
  - `app/config.py` — todas as variáveis de ambiente via `pydantic-settings`
  - `app/db/supabase_client.py` — cliente Supabase (service role key, singleton)
  - `app/models/` — schemas Pydantic para todas as entidades
  - `backend/.env.example` — placeholders conforme `docs/architecture.md`
- **Frontend React (Vite + Tailwind v4):**
  - `src/App.jsx` — React Router v6 com todas as rotas
  - `src/components/Layout.jsx` + `Sidebar.jsx` — layout com menu lateral completo
  - `src/components/ProtectedRoute.jsx` — protecção de rotas via Supabase Auth
  - `src/pages/Login.jsx` — página de login
  - `src/pages/` — páginas placeholder para todas as secções do painel
  - `src/lib/supabase.js` — cliente Supabase (anon key)
  - `src/lib/api.js` — wrapper REST para o backend (com auth header automático)
  - `src/i18n/pt.js` — strings PT-PT
  - `frontend/.env.example` — placeholders

## Decisões tomadas

- RLS não activado (conforme nota do `database-schema.md` — Fase 4)
- Auth middleware no backend como stub comentado — activar na Fase 4
- Tailwind v4 (via `@tailwindcss/vite`) — sem `tailwind.config.js` necessário
