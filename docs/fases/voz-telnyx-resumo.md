# Agente de voz (Telnyx) — resumo (19/10)

Número PT **+351 233 060 000**, chamadas recebidas, a funcionar de ponta a ponta (webhook → WebSocket de áudio → STT → Claude → TTS → `agente_chamadas`).
Testado com chamadas reais de 17 a 19/10. **Ainda é um agente à parte** (`claude_agent.py`, prompt `agente_config['voz']`); a direção é a voz ser um
**canal do motor** (um motor, N assistentes), fase própria por planear (`voz-como-canal-plano.md`, não escrito).

## Como funciona
- **Webhook** `POST /webhook/telnyx`: assinatura **Ed25519** verificada à mão (`timestamp|payload`, base64; o SDK `telnyx` 4.x dava 403). Segredos no Fly: `TELNYX_API_KEY`, `TELNYX_PUBLIC_KEY`, `TELNYX_PHONE_NUMBER`.
- **Áudio** PCMU 8 kHz em blocos de 20 ms. **VAD por energia adaptativa** (`vad.py`): fecha a frase após 700 ms de silêncio, limiar acompanha o ruído da linha (teto 1000; a chamada que abria logo com fala nunca detetava nada), guarda 200 ms de pré-roll e só 250 ms de cauda (700 ms de silêncio diluíam respostas curtas).
- **STT** `gpt-transcribe` (`STT_MODEL`; `gpt-4o-transcribe` devolvia o prompt como resposta). Normaliza o volume (até +12 dB), filtra alucinações («Legendas pela comunidade Amara.org») e o eco do prompt. **Resposta vazia → 2.ª tentativa** a 16 kHz com 300 ms de silêncio nas pontas e sem prompt; se ainda falhar a assistente pede para repetir (3 falhas seguidas → «linha má»).
- **TTS** `speak` da Telnyx, voz em `VOZ_TTS` (por omissão `Polly.Ines-Neural`; em produção `Azure.pt-PT-RaquelNeural`, sem diferença audível). Alternativas por testar: ElevenLabs (chave tua na Telnyx), Telnyx Ultra.
- **Saudação** (`SAUDACAO`): diz que é assistente virtual e que a chamada é transcrita; o prompt repete-a para nunca divergirem.
- **Telefone** é o da chamada (`from`), nunca pedido ao ouvido; pergunta fixa «Um consultor pode ligar-lhe para este mesmo número?».
- **Fim da chamada**: a despedida termina com a marca `FIM_CHAMADA` (nunca falada, tirada **antes** de `limpar_para_voz`, que apaga `_`); no `call.speak.ended` seguinte o webhook desliga.
- **Barge-in** existe atrás de `VOZ_BARGE_IN` (desligado) e **não foi testado**; `playback_stop` por confirmar.

## Por fazer
Barge-in; sessões em memória (perdem-se num restart, 1 máquina); «voz como canal do motor»; custo (`gpt-4o-mini-transcribe`) ou STT em tempo real; as respostas curtas ainda falham ~1 em 3 (sim, zona).
