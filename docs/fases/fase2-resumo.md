# Fase 2 — Resumo

**Data:** 2026-05-30
**Estado:** Implementada — aguarda teste com Telnyx real

## O que ficou feito

- **`agents/voice/session.py`** — `CallSession` dataclass + gestor em memória (create/get/remove)
- **`agents/voice/telnyx_api.py`** — chamadas async (httpx) à Telnyx REST API: answer, speak, stream_start, hangup
- **`agents/voice/stt.py`** — decodificação µ-law manual + WAV via stdlib + Whisper PT
- **`agents/voice/claude_agent.py`** — conversa com Claude Sonnet, persona carregada da tabela `config_agentes`
- **`agents/voice/save_call.py`** — extracção de dados pós-chamada via Claude tool use + upsert clientes + insert chamadas + insert leads
- **`agents/voice/webhook.py`** — `POST /webhook/telnyx`: verificação de assinatura Ed25519 (produção), handle `call.initiated`, `call.answered`, `call.speak.ended`, `call.hangup`
- **`agents/voice/audio_ws.py`** — `WS /ws/audio/{call_control_id}`: acumula 2s de áudio, STT, Claude, speak; retry "Pode repetir?" após 2 falhas STT
- **`main.py`** — routers registados
- **`requirements.txt`** — telnyx, openai, anthropic, httpx adicionados

## Decisões tomadas

- TTS via Telnyx `speak()` (REST), não via WebSocket — mais simples e fiável
- Áudio inbound-only (só ouvimos o cliente); resposta via `speak()`
- µ-law decodificado manualmente — sem dependência de `audioop` (removido no Python 3.13)
- Extracção de dados estruturados só no hangup (não durante a conversa)
- Assinatura do webhook ignorada em development; verificada em production

## Como testar

1. `cd backend && pip install -r requirements.txt`
2. Preencher `.env`: `TELNYX_API_KEY`, `TELNYX_PUBLIC_KEY`, `TELNYX_PHONE_NUMBER`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
3. `uvicorn app.main:app --reload`
4. `ngrok http 8000` → copiar URL HTTPS
5. Telnyx dashboard → Mission Control → Webhooks → URL: `https://xxxx.ngrok.io/webhook/telnyx`
6. Ligar para o número Telnyx
7. Verificar logs + Supabase (tabelas `chamadas`, `clientes`, `leads`)
