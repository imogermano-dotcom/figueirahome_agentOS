# Fase 2 — Plano: Agente de Voz

**Data:** 2026-05-30
**Estado:** Em implementação

## Objectivo

Sistema atende chamadas Telnyx, conversa em PT-PT (Whisper + Claude + TTS), e grava cliente + lead + transcrição + resumo no Supabase.

## Decisões do utilizador

| Decisão | Escolha |
|---|---|
| Voz TTS | `Polly.Ines-Neural` (feminina, natural) |
| Confirmação de dados | Sim — agente lê os dados em voz alta antes de terminar |
| STT falha 2× seguidas | Pede para repetir: "Desculpe, não percebi. Pode repetir, por favor?" |
| Horário de funcionamento | 24/7 |

## Tarefas

| # | Ficheiro | Descrição |
|---|---|---|
| 1 | `docs/fases/fase2-plano.md` | Este ficheiro |
| 2 | `backend/requirements.txt` | Adicionar telnyx, openai, anthropic, httpx |
| 3 | `backend/app/agents/voice/session.py` | CallSession + gestor de sessões em memória |
| 4 | `backend/app/agents/voice/telnyx_api.py` | Chamadas REST à Telnyx (answer, speak, stream, hangup) |
| 5 | `backend/app/agents/voice/stt.py` | Whisper STT (PT) |
| 6 | `backend/app/agents/voice/claude_agent.py` | Conversa com Claude usando persona da DB |
| 7 | `backend/app/agents/voice/save_call.py` | Extrair dados + gravar no Supabase |
| 8 | `backend/app/agents/voice/webhook.py` | POST /webhook/telnyx |
| 9 | `backend/app/agents/voice/audio_ws.py` | WS /ws/audio/{call_control_id} |
| 10 | `backend/app/main.py` | Registar routers |

## Arquitectura do fluxo de chamada

```
1. Telnyx → POST /webhook/telnyx (call.initiated)
   → answer() via REST Telnyx API

2. Telnyx → POST /webhook/telnyx (call.answered)
   → stream_start() → Telnyx conecta ao WS
   → speak() → saudação inicial

3. Telnyx → WS /ws/audio/{id} (chunks de áudio PCMU)
   → acumular 2 segundos
   → decode µ-law → WAV
   → Whisper STT (PT)
   → Claude API (persona da config_agentes)
   → speak() via REST → is_speaking = True

4. Telnyx → POST /webhook/telnyx (call.speak.ended)
   → is_speaking = False → volta a ouvir

5. Telnyx → POST /webhook/telnyx (call.hangup)
   → Claude extrai dados estruturados da transcrição
   → Claude gera resumo
   → Supabase: upsert clientes, insert chamadas, insert leads
```

## Dependências novas

| Pacote | Motivo |
|---|---|
| `telnyx` | Verificação de assinatura do webhook (Ed25519) |
| `openai` | Whisper STT |
| `anthropic` | Claude API (conversa + extracção de dados) |
| `httpx` | Chamadas async à REST API da Telnyx |

## Como testar

1. Backend a correr localmente: `uvicorn app.main:app --reload`
2. ngrok a expor porta 8000: `ngrok http 8000`
3. Telnyx dashboard → configurar webhook URL: `https://xxxx.ngrok.io/webhook/telnyx`
4. Ligar para o número Telnyx
5. Verificar: agente atende, conversa, recolhe dados
6. Após chamada: verificar Supabase → tabelas `chamadas`, `clientes`, `leads`
