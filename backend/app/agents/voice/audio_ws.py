import base64
import json
import logging
import time
from difflib import SequenceMatcher

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
_SILENCIO_S = 8  # ninguém fala depois de a assistente acabar: pergunta se está lá
_AVISOS_ATE_DESLIGAR = 2
_ESTA_LA = "Está aí? Se preferir, um consultor liga-lhe depois para este número."
_ADEUS_SILENCIO = "Não consigo ouvi-lo. Um consultor volta a ligar-lhe. Obrigada e até breve."
_REPETICOES_ATE_DESISTIR = 2  # à 3.ª pergunta quase igual seguida desiste: 28/10 repetiu a mesma pergunta 3 vezes
_DESISTIR = "Parece que a linha está má e não o consigo ouvir bem. Um consultor liga-lhe para este número. Obrigada e até breve."
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
                if detetor.curta_ms:
                    logger.info("[%s] fala de %.0f ms descartada por curta (limiar %.0f)", call_control_id[-6:],
                                detetor.curta_ms, detetor.limiar)
                    detetor.curta_ms = 0.0
                if detetor.fala_ignorada_ms:
                    logger.info("[%s] %.0f ms de fala ignorada enquanto a assistente falava", call_control_id[-6:],
                                detetor.fala_ignorada_ms)
                    detetor.fala_ignorada_ms = 0.0
                if session.is_speaking and detetor.fala_ms >= _BARGE_IN_MS:
                    # Só chega aqui com o barge-in ligado. O áudio é a faixa de entrada: o TTS dela não volta.
                    logger.info("[%s] barge-in: a pessoa falou por cima, TTS cortado", call_control_id[-6:])
                    session.is_speaking = False
                    await telnyx_api.parar_fala(call_control_id)
                if frase and not session.is_speaking:
                    await _process_turn(session, call_control_id, frase, detetor.ultima)
                elif not session.is_speaking and detetor.fala_ms == 0:
                    await _verificar_silencio(session, call_control_id)

            elif event == "stop":
                break

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Erro no WebSocket da chamada %s", call_control_id)


async def _verificar_silencio(session, call_control_id: str) -> None:
    """18:21 de 27/10: a pessoa respondeu e o detetor não apanhou (ou calou-se), e a chamada ficou muda até ela
    desligar. Passados `_SILENCIO_S` sem fala, pergunta; à 2.ª vez sem resposta despede-se e desliga."""
    if session.silencio_desde is None or time.monotonic() - session.silencio_desde < _SILENCIO_S:
        return
    session.silencio_desde = None
    session.avisos_silencio += 1
    session.is_speaking = True
    if session.avisos_silencio > _AVISOS_ATE_DESLIGAR:
        session.terminar = True
        await telnyx_api.speak(call_control_id, _ADEUS_SILENCIO)
    else:
        await telnyx_api.speak(call_control_id, _ESTA_LA)


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


def _e_repeticao(session, resposta: str) -> bool:
    """Quase igual à resposta anterior (o modelo só troca o nome ou uma palavra): conta; senão zera."""
    antes, session.ultima_resposta = session.ultima_resposta, resposta.lower()
    igual = bool(antes) and SequenceMatcher(None, antes, session.ultima_resposta).ratio() >= 0.8
    session.repeticoes = session.repeticoes + 1 if igual else 0
    return session.repeticoes >= _REPETICOES_ATE_DESISTIR


async def _process_turn(session, call_control_id: str, audio_bytes: bytes, energia: dict | None = None) -> None:
    """Uma frase completa (o detetor já esperou pelo silêncio). Texto vazio = fala que o STT não percebeu."""
    session.silencio_desde = None
    t0 = time.monotonic()
    text = await transcribe(audio_bytes)
    e = energia or {}
    logger.info("[%s] frase de %.1fs → STT (%.1fs): %r | energia pico %.0f média %.0f limiar %.0f", call_control_id[-6:],
                len(audio_bytes) / 8000, time.monotonic() - t0, text, e.get("pico", 0), e.get("media", 0), e.get("limiar", 0))

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
    session.avisos_silencio = 0
    session.transcricao_acumulada += f"\nCliente: {text}"

    t1 = time.monotonic()
    if settings.voz_como_canal:
        response_text = await resposta_do_motor(session, text)
    else:
        response_text = await get_response(session, text)
    if _e_repeticao(session, response_text):
        response_text = _DESISTIR
        session.terminar = True
    session.transcricao_acumulada += f"\nAgente: {response_text}"
    logger.info("[%s] Claude (%.1fs): %r", call_control_id[-6:], time.monotonic() - t1, response_text)

    session.is_speaking = True
    await telnyx_api.speak(call_control_id, response_text)
