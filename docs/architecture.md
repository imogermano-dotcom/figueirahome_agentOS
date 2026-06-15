# Architecture — Figueirahome Agent Call

> Decisões técnicas, fluxos e justificações. Complementa o `CLAUDE.md`.

---

## Diagrama geral

```
        CHAMADA TELEFÓNICA
               │
               ▼
        ┌──────────────┐
        │    TELNYX     │  Call Control + Media Streaming
        └──────┬───────┘
               │ WebSocket (áudio em chunks de ~20ms, base64 RTP)
               ▼
        ┌──────────────────────────────┐
        │   BACKEND FastAPI (Fly.io)    │
        │  ┌────────────────────────┐   │
        │  │  Agente 1 — Voz        │   │  STT (Whisper) → Claude API → TTS (Telnyx)
        │  └────────────────────────┘   │
        │  ┌────────────────────────┐   │
        │  │  Agente 2 — Broker     │   │  Claude API + tool calling → Supabase
        │  └────────────────────────┘   │
        │  ┌────────────────────────┐   │
        │  │  API do Painel (/api)  │   │  CRUD clientes/imoveis/leads
        │  └────────────────────────┘   │
        └──────────┬───────────────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │      SUPABASE         │  PostgreSQL + Auth + Realtime
        └──────────┬───────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │  FRONTEND React       │  Painel de gestão (Vercel)
        │  (Vercel)             │  Auth via Supabase
        └──────────────────────┘
```

---

## Decisões e justificações

### Porquê API directa do Claude e não o Agent SDK
O caso de uso é conversa + consulta de dados, não execução autónoma de tarefas complexas (ler ficheiros, correr comandos). A API directa com tool calling chega e é mais simples. Custo = só tokens.

### Porquê o backend não pode ser serverless
O streaming de áudio da Telnyx exige uma **conexão WebSocket aberta durante toda a chamada**. Plataformas serverless (Vercel functions, etc.) fecham conexões ao fim de segundos. Por isso o backend corre em Fly.io (conexões persistentes, servidores na Europa = baixa latência).

### Porquê Fly.io e não VPS
Fly.io é gerido (sem manutenção de servidor, restart automático, SSL automático) e tem servidores próximos de Portugal. Para uma agência onde uma chamada perdida tem custo, a fiabilidade de uma plataforma gerida compensa o pequeno custo extra face a um VPS.

### Porquê Supabase
PostgreSQL gerido + Auth + Realtime + API automática num só serviço. Reduz código de infraestrutura. O Realtime permite que o painel reflicta novos clientes/leads em tempo real.

### Frontend separado do backend
React na Vercel (estático, CDN, gratuito) + FastAPI na Fly.io. O frontend fala com o backend via REST e com o Supabase via Auth.

---

## Latência no Agente de Voz (crítico)

Para a conversa fluir naturalmente:
- Processar áudio em **chunks** à medida que chega, não esperar pela frase completa.
- A Telnyx envia pacotes de ~20ms — começar inferência cedo.
- Considerar streaming de resposta do Claude (token a token) para começar o TTS mais cedo.
- Manter o histórico da conversa em memória durante a chamada (não ir à base de dados a cada turno).

---

## Segurança

- Segredos só em variáveis de ambiente (`.env`, nunca commitados).
- Verificar a **assinatura dos webhooks da Telnyx** para rejeitar pedidos falsos.
- Backend usa a **service role key** do Supabase; o frontend usa a **anon key** + Auth.
- Endpoints `/api/*` protegidos por token de autenticação.
- RLS activado no Supabase em produção.

---

## Variáveis de ambiente

### Backend (`backend/.env.example`)
```
# Anthropic
ANTHROPIC_API_KEY=YOUR_ANTHROPIC_API_KEY

# Telnyx
TELNYX_API_KEY=YOUR_TELNYX_API_KEY
TELNYX_PUBLIC_KEY=YOUR_TELNYX_WEBHOOK_PUBLIC_KEY
TELNYX_PHONE_NUMBER=YOUR_TELNYX_PHONE_NUMBER

# Supabase
SUPABASE_URL=YOUR_SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY=YOUR_SUPABASE_SERVICE_ROLE_KEY

# OpenAI (Whisper STT)
OPENAI_API_KEY=YOUR_OPENAI_API_KEY

# App
APP_BASE_URL=https://your-backend.fly.dev
ENVIRONMENT=development
```

### Frontend (`frontend/.env.example`)
```
VITE_SUPABASE_URL=YOUR_SUPABASE_URL
VITE_SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY
VITE_API_BASE_URL=http://localhost:8000
```

---

## Roadmap técnico resumido

| Fase | Entrega | Estado |
|---|---|---|
| 1 | Estrutura + Supabase + base FastAPI + base React + Auth | **Actual** |
| 2 | Agente de Voz (Telnyx + Whisper + Claude + TTS) | Pendente |
| 3 | Agente Broker (chat web + canais) | Pendente |
| 4 | Painel completo (dashboard, gestão, config, histórico) | Pendente |
| 5 | Inglês, portais, relatórios, mobile | Futuro |
