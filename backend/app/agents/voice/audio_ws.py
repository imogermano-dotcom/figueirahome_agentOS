import base64
import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agents.voice import session as session_mgr
from app.agents.voice import telnyx_api
from app.agents.voice.claude_agent import FIM_CHAMADA, get_response, limpar_para_voz
from app.agents.voice.stt import transcribe
from app.agents.voice.vad import DetetorDeFrase
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

_STT_RETRY_MSG = "Desculpe, não percebi. Pode repetir, por favor?"
_STT_LINHA_MA = "A linha parece estar má. Se preferir, um consultor liga-lhe para este número. Pode repetir, por favor?"
_ERRO_DO_MOTOR = "Ocorreu um erro. Tenta novamente."  # `engine._ERRO`: dito em voz alta, é melhor pedir para repetir
_FALHAS_ATE_LINHA_MA = 3  # à 3.ª falha seguida muda a mensagem, para não repetir a mesma frase
_BARGE_IN_MS = 400  # fala contínua por cima da assistente para a cortar (um estalido não a corta)


@router.websocket("/ws/audio/{call_control_id}")
async def audio_websocket(websocket: WebSocket, call_control_id: str):
    await websocket.accept()
    session = session_mgr.get_session(call_control_id)
    detetor = DetetorDeFrase()

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "media":
                if session is None:
                    continue
                bloco = base64.b64decode(msg["media"]["payload"])
                if session.is_speaking and not settings.voz_barge_in:
                    detetor.escutar(bloco)  # nunca abre frase, mas guarda o início do que vem a seguir
                    continue

                frase = detetor.feed(bloco)
                if session.is_speaking and detetor.fala_ms >= _BARGE_IN_MS:
                    # Só chega aqui com o barge-in ligado. O áudio é a faixa de entrada: o TTS dela não volta.
                    logger.info("[%s] barge-in: a pessoa falou por cima, TTS cortado", call_control_id[-6:])
                    session.is_speaking = False
                    await telnyx_api.parar_fala(call_control_id)
                if frase and not session.is_speaking:
                    await _process_turn(session, call_control_id, frase)

            elif event == "stop":
                break

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Erro no WebSocket da chamada %s", call_control_id)


async def resposta_do_motor(session, texto: str) -> str:
    """A resposta do motor dos assistentes (canal `voz`), limpa para o TTS. O `FIM_CHAMADA` é tirado antes da limpeza
    (o `_` é um símbolo que ela apaga) e desliga a chamada quando a fala acabar, como no agente antigo."""
    from app.agents.broker import engine  # import tardio: o motor importa este módulo (`claude_agent`)

    bruto = await engine.responder("voz", session.call_control_id, texto, telefone=session.numero_origem)
    if FIM_CHAMADA in bruto:
        session.terminar = True
        bruto = bruto.replace(FIM_CHAMADA, "")
    if bruto.strip() == _ERRO_DO_MOTOR:
        bruto = ""
    return limpar_para_voz(bruto) or "Desculpe, não percebi bem. Pode repetir, por favor?"


async def _process_turn(session, call_control_id: str, audio_bytes: bytes) -> None:
    """Uma frase completa (o detetor já esperou pelo silêncio). Texto vazio = fala que o STT não percebeu."""
    t0 = time.monotonic()
    text = await transcribe(audio_bytes)
    logger.info("[%s] frase de %.1fs → STT (%.1fs): %r", call_control_id[-6:], len(audio_bytes) / 8000,
                time.monotonic() - t0, text)

    if not text or len(text.strip()) < 2:
        # O detetor só entrega frases com fala: texto vazio é o STT a falhar, não a pessoa calada. Calar-se aqui
        # deixava a chamada morta (18/10: o nome dito a seguir à pergunta nunca teve resposta).
        session.stt_fail_count += 1
        aviso = _STT_RETRY_MSG if session.stt_fail_count < _FALHAS_ATE_LINHA_MA else _STT_LINHA_MA
        if session.stt_fail_count >= _FALHAS_ATE_LINHA_MA:
            session.stt_fail_count = 0
        session.is_speaking = True
        await telnyx_api.speak(call_control_id, aviso)
        return

    session.stt_fail_count = 0
    session.transcricao_acumulada += f"\nCliente: {text}"

    t1 = time.monotonic()
    if settings.voz_como_canal:
        response_text = await resposta_do_motor(session, text)
    else:
        response_text = await get_response(session, text)
    session.transcricao_acumulada += f"\nAgente: {response_text}"
    logger.info("[%s] Claude (%.1fs): %r", call_control_id[-6:], time.monotonic() - t1, response_text)

    session.is_speaking = True
    await telnyx_api.speak(call_control_id, response_text)
