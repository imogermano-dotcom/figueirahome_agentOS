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


def test_escutar_nunca_abre_frase_enquanto_a_assistente_fala():
    det = vad.DetetorDeFrase()
    for b in [FALA] * 100:
        assert det.escutar(b) is None
    assert _alimenta(det, [SILENCIO] * 60) == [], "o que se ouviu durante a fala dela não vira frase"


def test_escutar_guarda_o_inicio_da_resposta_dita_quando_a_assistente_acaba():
    """18/10: o nome dito logo a seguir à pergunta perdia-se porque tudo era descartado enquanto ela falava."""
    det = vad.DetetorDeFrase()
    for b in [SILENCIO] * 30 + [FALA] * 4:  # a pessoa começa 80 ms antes de a assistente acabar
        det.escutar(b)
    frases = _alimenta(det, [FALA] * 30 + [SILENCIO] * 40)
    assert len(frases) == 1
    assert FALA * 34 in frases[0], "os 4 blocos ditos durante a fala da assistente + os 30 seguintes, sem corte"


def test_escutar_descarta_a_frase_que_estava_a_meio():
    det = vad.DetetorDeFrase()
    _alimenta(det, [FALA] * 30)
    det.escutar(SILENCIO)
    assert _alimenta(det, [SILENCIO] * 60) == []


def _bloco_com_rms(alvo: int) -> bytes:
    """20 ms de onda quadrada com amplitude ≈ `alvo` (RMS = amplitude)."""
    from app.agents.voice import stt
    import struct
    b = min(range(0x80), key=lambda x: abs(struct.unpack("<h", stt._ulaw2lin(bytes([x | 0x80])))[0] - alvo))
    return bytes([b | 0x80, b]) * 80  # |x|, -|x|


def test_ruido_de_linha_acima_do_limiar_fixo_nao_impede_o_fim_da_frase():
    """17/10: ruído de ~300 (> 200) nunca era «silêncio» e a frase só fechava aos 15 s."""
    ruido, fala = _bloco_com_rms(300), _bloco_com_rms(3000)
    det = vad.DetetorDeFrase()
    frases = _alimenta(det, [ruido] * 150 + [fala] * 50 + [ruido] * 60)
    assert len(frases) == 1, "a frase fecha 700 ms depois de a fala parar, apesar do ruído"
    assert len(frases[0]) < 15 * 8000, "e não é o teto de 15 s"
    assert det.limiar > 300, "o limiar subiu acima do ruído"


def test_so_ruido_de_linha_nunca_devolve_frase():
    assert _alimenta(vad.DetetorDeFrase(), [_bloco_com_rms(300)] * 600) == []


def test_nos_primeiros_200_ms_nada_e_fala_e_o_ruido_nao_gera_frase_fantasma():
    det = vad.DetetorDeFrase()
    assert _alimenta(det, [_bloco_com_rms(300)] * 100) == []


def test_limpar_para_voz_tira_o_que_o_tts_leria_em_voz_alta():
    from app.agents.voice.claude_agent import limpar_para_voz
    sujo = "Deixe-me pesquisar.\n\n[A usar tool pesquisar_imoveis com: tipo=arrendamento]\n\nPode confirmar o **telefone**?"
    assert limpar_para_voz(sujo) == "Deixe-me pesquisar. Pode confirmar o telefone?"
    assert limpar_para_voz("[só isto]") == ""


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


def _ws_com_stt(monkeypatch, textos):
    """Uma frase por texto em `textos` (o STT devolve-os por ordem); regista o que a assistente diz."""
    ditas, claude, fila = [], [], list(textos)

    async def _transcribe(_audio):
        return fila.pop(0)

    async def _resposta(_s, texto):
        claude.append(texto)
        return "Qual é o seu orçamento?"

    async def _speak(_id, texto):
        ditas.append(texto)

    monkeypatch.setattr(audio_ws, "transcribe", _transcribe)
    monkeypatch.setattr(audio_ws, "get_response", _resposta)
    monkeypatch.setattr(audio_ws.telnyx_api, "speak", _speak)
    sessao = session_mgr.create_session("ws-e", "+351912345678")
    app = FastAPI()
    app.include_router(audio_ws.router)
    with TestClient(app).websocket_connect("/ws/audio/ws-e") as ws:
        for _ in textos:
            sessao.is_speaking = False  # a assistente acabou: a pessoa fala outra frase
            for bloco in [FALA] * 60 + [SILENCIO] * 40:
                ws.send_text(_media(bloco))
        ws.send_text(json.dumps({"event": "stop"}))
    session_mgr.remove_session("ws-e")
    return ditas, claude


def test_stt_vazio_a_1_falha_a_assistente_pede_que_repita(monkeypatch):
    """18/10: texto vazio ao 1.º erro era ignorado e a chamada ficava morta."""
    ditas, claude = _ws_com_stt(monkeypatch, [""])
    assert ditas == [audio_ws._STT_RETRY_MSG] and claude == []


def test_stt_vazio_tres_vezes_muda_a_mensagem_e_volta_a_contar(monkeypatch):
    ditas, _ = _ws_com_stt(monkeypatch, ["", "", "", ""])
    assert ditas == [audio_ws._STT_RETRY_MSG, audio_ws._STT_RETRY_MSG, audio_ws._STT_LINHA_MA, audio_ws._STT_RETRY_MSG]


def test_texto_curto_de_duas_letras_conta_como_resposta(monkeypatch):
    ditas, claude = _ws_com_stt(monkeypatch, ["Ok"])
    assert claude == ["Ok"] and ditas == ["Qual é o seu orçamento?"]


def test_uma_frase_boa_zera_as_falhas(monkeypatch):
    ditas, claude = _ws_com_stt(monkeypatch, ["", "quero um T2", "", ""])
    assert ditas == [audio_ws._STT_RETRY_MSG, "Qual é o seu orçamento?", audio_ws._STT_RETRY_MSG, audio_ws._STT_RETRY_MSG]


def _ws_barge_in(monkeypatch, ligado):
    """Assistente a falar; a pessoa fala por cima. Devolve (turnos, paragens, sessão)."""
    turnos, paragens = [], []
    monkeypatch.setattr(audio_ws.settings, "voz_barge_in", ligado)

    async def _parar(_id):
        paragens.append(_id)

    monkeypatch.setattr(audio_ws.telnyx_api, "parar_fala", _parar)
    sessao = session_mgr.create_session("ws-b", "+351912345678")
    sessao.is_speaking = True
    with _cliente(monkeypatch, turnos).websocket_connect("/ws/audio/ws-b") as ws:
        for bloco in [SILENCIO] * 20 + [FALA] * 60 + [SILENCIO] * 40:
            ws.send_text(_media(bloco))
        ws.send_text(json.dumps({"event": "stop"}))
    session_mgr.remove_session("ws-b")
    return turnos, paragens, sessao


def test_barge_in_ligado_corta_a_fala_e_responde_a_pessoa(monkeypatch):
    turnos, paragens, sessao = _ws_barge_in(monkeypatch, True)
    assert paragens == ["ws-b"], "o TTS foi cortado uma vez"
    assert [t[0] for t in turnos] == ["stt", "claude", "speak"], turnos


def test_barge_in_desligado_por_omissao_nada_acontece(monkeypatch):
    assert audio_ws.settings.voz_barge_in is False
    turnos, paragens, _ = _ws_barge_in(monkeypatch, False)
    assert paragens == [] and turnos == []


def test_estalido_por_cima_da_assistente_nao_a_corta(monkeypatch):
    turnos, paragens = [], []
    monkeypatch.setattr(audio_ws.settings, "voz_barge_in", True)

    async def _parar(_id):
        paragens.append(_id)

    monkeypatch.setattr(audio_ws.telnyx_api, "parar_fala", _parar)
    sessao = session_mgr.create_session("ws-c", "+351912345678")
    sessao.is_speaking = True
    with _cliente(monkeypatch, turnos).websocket_connect("/ws/audio/ws-c") as ws:
        for bloco in [SILENCIO] * 20 + [FALA] * 8 + [SILENCIO] * 40:  # 160 ms de fala
            ws.send_text(_media(bloco))
        ws.send_text(json.dumps({"event": "stop"}))
    session_mgr.remove_session("ws-c")
    assert paragens == [] and sessao.is_speaking is True


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
