# Fase 3a — Plano: Agente Broker + Canal WhatsApp (Meta Official API)

## Objectivo
Agente Broker com acesso à DB, acessível via WhatsApp (Meta Cloud API) e web chat.

## Ficheiros criados/alterados

| Acção | Ficheiro |
|---|---|
| Alterado | `backend/app/config.py` — vars Meta |
| Alterado | `backend/.env.example` — placeholders Meta |
| Alterado | `backend/app/main.py` — routers registados |
| Criado | `backend/app/agents/broker/tools.py` |
| Criado | `backend/app/agents/broker/conversation.py` |
| Criado | `backend/app/agents/broker/claude_agent.py` |
| Criado | `backend/app/agents/broker/channels/whatsapp/meta_api.py` |
| Criado | `backend/app/agents/broker/channels/whatsapp/webhook.py` |
| Criado | `backend/app/api/broker.py` |

## Env vars novas
```
META_WHATSAPP_TOKEN=
META_APP_SECRET=
META_PHONE_NUMBER_ID=
META_VERIFY_TOKEN=
META_API_VERSION=v19.0
```

## Endpoints
- `GET /webhook/whatsapp` — verificação Meta
- `POST /webhook/whatsapp` — receber mensagens WhatsApp
- `POST /api/broker/chat` — chat web

## Como testar
1. Servidor: `uvicorn app.main:app --reload` em `backend/`
2. Web chat: `POST /api/broker/chat` via `/docs`
3. WhatsApp: ngrok + configurar webhook Meta + enviar mensagem
