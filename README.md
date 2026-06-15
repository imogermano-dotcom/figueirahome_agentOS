# Figueirahome Agent Call — Setup

Plataforma de IA para agência imobiliária: agente de voz + assistente de broker + painel de gestão.

## Como usar estes ficheiros no Cursor

1. Cria a pasta do projecto e copia todos estes ficheiros para lá, mantendo a estrutura:
   ```
   figueirahome-agent-call/
   ├── CLAUDE.md
   ├── README.md
   └── docs/
       ├── PRD.md
       ├── database-schema.md
       ├── api-spec.md
       └── architecture.md
   ```
2. Abre a pasta no Cursor.
3. Abre o Claude Code e cola a "mensagem de arranque" abaixo.

O Claude Code vai ler o `CLAUDE.md` automaticamente e seguir o plano, começando pela Fase 1.

---

## Mensagem de arranque (cola isto no Claude Code)

> Lê o `CLAUDE.md` e os ficheiros em `docs/` para entenderes o projecto Figueirahome Agent Call.
>
> Vamos começar a **Fase 1 — Fundação**. Implementa, por esta ordem:
>
> 1. A estrutura de pastas completa do projecto (backend FastAPI + frontend React + supabase/migrations), conforme o `CLAUDE.md`.
> 2. A migration SQL com todas as tabelas, em `supabase/migrations/0001_initial_schema.sql`, exactamente como no `docs/database-schema.md`.
> 3. O servidor FastAPI base: `main.py` com endpoint `GET /health`, configuração via `config.py` que lê variáveis de ambiente, e o cliente Supabase em `db/`.
> 4. Os ficheiros `.env.example` no backend e no frontend, com os placeholders do `docs/architecture.md`.
> 5. O frontend React (Vite + Tailwind) base: routing, layout do painel com o menu lateral (Dashboard, Agente 1, Agente 2, Clientes, Imóveis, Leads, Config), e o cliente Supabase em `src/lib/`.
> 6. Autenticação do painel via Supabase Auth (página de login + protecção de rotas).
>
> Não avances para os agentes (Fases 2 e 3) — implementa só a fundação. No fim, actualiza a checklist do "Estado actual" no `CLAUDE.md` e diz-me como testar localmente.
>
> Usa sempre os placeholders das credenciais, nunca valores reais. Pergunta se tiveres dúvidas antes de adicionar dependências não previstas.

---

## Depois da Fase 1

Quando a fundação estiver pronta e testada, arranca a fase seguinte com algo como:

> Fase 1 validada. Actualiza o `CLAUDE.md` e começa a **Fase 2 — Agente de Voz**, seguindo o `docs/api-spec.md` e `docs/architecture.md`.

---

## Pré-requisitos a instalar

- Node.js (para o frontend React/Vite)
- Python 3.11+ (para o backend FastAPI)
- Conta Supabase (criar projecto e correr a migration)
- Conta Telnyx (Fase 2)
- API keys: Anthropic, OpenAI (Fase 2)
