"""Voz: deteção de fim de frase (`app/agents/voice/vad.py`) e o WebSocket que a usa.

Corre com `pytest backend/tests/` ou `python backend/tests/test_voz_vad.py`. Sem rede nem credenciais.
Caso real de 17/10: janelas fixas de 2 s cortavam a frase («Um, uma casa, uma cidade...») e a assistente respondia ao fragmento.
"""

import base64
import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.voice import audio_ws, vad  # noqa: E402
from app.agents.voice import session as session_mgr  # noqa: E402

FALA = b"\x00\x80" * 80      # 20 ms a ±32124
SILENCIO = b"\xff" * 160    # 20 ms a zero


def _alimenta(det, blocos):
    return [r for b in blocos if (r := det.feed(b)) is not None]


def test_so_silencio_nunca_devolve_frase():
    assert _alimenta(vad.DetetorDeFrase(), [SILENCIO] * 500) == []


def test_frase_so_fecha_depois_do_silencio():
    det = vad.DetetorDeFrase()
    assert _alimenta(det, [FALA] * 50) == [], "enquanto fala não há frase"
    assert _alimenta(det, [SILENCIO] * 30) == [], "600 ms de silêncio ainda não fecham"
    frases = _alimenta(det, [SILENCIO] * 10)
    assert len(frases) == 1 and len(frases[0]) >= 50 * 160, "700 ms fecham, e a frase traz a fala inteira"


def test_pausa_curta_no_meio_nao_parte_a_frase():
    det = vad.DetetorDeFrase()
    frases = _alimenta(det, [FALA] * 25 + [SILENCIO] * 15 + [FALA] * 25 + [SILENCIO] * 40)
    assert len(frases) == 1, "300 ms de pausa não é fim de frase"
    assert len(frases[0]) >= 65 * 160


def test_estalido_curto_e_descartado():
    det = vad.DetetorDeFrase()
    assert _alimenta(det, [FALA] * 5 + [SILENCIO] * 60) == [], "100 ms de fala não chegam"


def test_pre_roll_guarda_o_inicio_da_frase():
    det = vad.DetetorDeFrase()
    frases = _alimenta(det, [SILENCIO] * 100 + [FALA] * 30 + [SILENCIO] * 40)
    assert len(frases) == 1
    assert frases[0].startswith(SILENCIO), "200 ms de lead-in antes da fala"
    assert len(frases[0]) < (100 + 30) * 160, "mas não o silêncio todo"


def test_ruido_continuo_e_cortado_aos_15_s():
    det = vad.DetetorDeFrase()
    frases = _alimenta(det, [FALA] * 800)  # 16 s sem pausa
    assert len(frases) == 1 and len(frases[0]) <= vad.MAX_FRASE_MS * 8 + 160


def test_reset_descarta_o_que_estava_a_meio():
    det = vad.DetetorDeFrase()
    _alimenta(det, [FALA] * 30)
    det.reset()
    assert _alimenta(det, [SILENCIO] * 60) == []


def _media(bloco):
    return json.dumps({"event": "media", "media": {"payload": base64.b64encode(bloco).decode()}})


def _cliente(monkeypatch, turnos):
    async def _transcribe(audio):
        turnos.append(("stt", len(audio)))
        return "quero um T2 na Figueira"

    async def _resposta(_s, texto):
        turnos.append(("claude", texto))
        return "Qual é o seu orçamento?"

    async def _speak(_id, texto):
        turnos.append(("speak", texto))

    monkeypatch.setattr(audio_ws, "transcribe", _transcribe)
    monkeypatch.setattr(audio_ws, "get_response", _resposta)
    monkeypatch.setattr(audio_ws.telnyx_api, "speak", _speak)
    app = FastAPI()
    app.include_router(audio_ws.router)
    return TestClient(app)


def test_websocket_uma_resposta_por_frase_e_nenhuma_ao_silencio(monkeypatch):
    turnos = []
    sessao = session_mgr.create_session("ws-1", "+351912345678")
    with _cliente(monkeypatch, turnos).websocket_connect("/ws/audio/ws-1") as ws:
        for _ in range(200):
            ws.send_text(_media(SILENCIO))                       # espera: não responde
        for bloco in [FALA] * 60 + [SILENCIO] * 40:              # uma frase
            ws.send_text(_media(bloco))
        ws.send_text(json.dumps({"event": "stop"}))
    assert [t[0] for t in turnos] == ["stt", "claude", "speak"], turnos
    assert sessao.is_speaking is True and "quero um T2" in sessao.transcricao_acumulada
    session_mgr.remove_session("ws-1")


def test_websocket_ignora_o_que_chega_enquanto_a_assistente_fala(monkeypatch):
    turnos = []
    sessao = session_mgr.create_session("ws-2", "+351912345678")
    sessao.is_speaking = True
    with _cliente(monkeypatch, turnos).websocket_connect("/ws/audio/ws-2") as ws:
        for bloco in [FALA] * 60 + [SILENCIO] * 40:
            ws.send_text(_media(bloco))
        ws.send_text(json.dumps({"event": "stop"}))
    assert turnos == []
    session_mgr.remove_session("ws-2")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
