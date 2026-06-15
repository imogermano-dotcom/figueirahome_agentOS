# Fase 3a — Resumo: Agente Broker + Canal WhatsApp

**Data:** 2026-06-08
**Estado:** Código completo, não testado com credenciais reais Meta.

## O que foi implementado

### Agente Broker Core
- **`tools.py`** — 3 tools Claude API: `consultar_clientes`, `consultar_imoveis`, `consultar_leads` com filtros opcionais. Queries assíncronas via Supabase.
- **`conversation.py`** — Carrega e guarda histórico de conversas em `agente_conversas`. Upsert por `canal` + `participante`.
- **`claude_agent.py`** — Motor de chat: carrega config do broker em `agente_config`, chama Claude `claude-sonnet-4-6` com tools, executa tool calls em loop (máx 5 iterações), guarda histórico.

### Canal WhatsApp (Meta Cloud API)
- **`meta_api.py`** — `send_text_message()` com split automático se > 4000 chars; `mark_as_read()`.
- **`webhook.py`** — `GET /webhook/whatsapp` para verificação Meta; `POST /webhook/whatsapp` com processamento em background (retorna 200 imediatamente). Verifica assinatura X-Hub-Signature-256 com App Secret em produção.

### Web Chat
- **`api/broker.py`** — `POST /api/broker/chat` para chat directo (painel web futuro).

## Decisões

- Assinatura HMAC usa `meta_app_secret`, não o token de acesso (comportamento correcto da Meta API).
- Processamento WhatsApp em `BackgroundTask` — Meta exige resposta HTTP < 20s.
- Tipos de mensagem não-texto ignorados silenciosamente (imagens, áudio, etc.).
- Histórico de conversa por `canal` + `participante` (número de telefone no WhatsApp).

## Como testar (web chat, sem Meta)

```bash
cd backend
uvicorn app.main:app --reload
# Abrir http://localhost:8000/docs
# POST /api/broker/chat com {"mensagem": "que imoveis tens?"}
```

## Como configurar WhatsApp real

1. Criar Meta App em developers.facebook.com
2. Adicionar produto "WhatsApp"
3. Configurar webhook: `https://<ngrok>/webhook/whatsapp`, verify token = `META_VERIFY_TOKEN`
4. Preencher `.env` com `META_WHATSAPP_TOKEN`, `META_APP_SECRET`, `META_PHONE_NUMBER_ID`, `META_VERIFY_TOKEN`
