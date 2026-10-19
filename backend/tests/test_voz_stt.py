"""Voz: descodificador µ-law, deteção de silêncio e filtro de alucinações do Whisper (`app/agents/voice`).

Corre com `pytest backend/tests/` ou `python backend/tests/test_voz_stt.py`. Sem rede nem credenciais.
Caso real de 17/10: o descodificador dava metade da amplitude e o Whisper devolvia «Legendas pela comunidade Amara.org».
"""

import asyncio
import struct
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.voice import session as session_mgr  # noqa: E402
from app.agents.voice import stt, webhook  # noqa: E402
from app.config import settings  # noqa: E402


def _amostra(byte: int) -> int:
    return struct.unpack("<h", stt._ulaw2lin(bytes([byte])))[0]


def test_ulaw_valores_de_referencia_g711():
    assert _amostra(0x00) == -32124 and _amostra(0x80) == 32124, "extremos"
    assert _amostra(0xFF) == 0 and _amostra(0x7F) == 0, "zero (os dois sinais)"
    assert _amostra(0x10) == -15996 and _amostra(0x40) == -1884


def test_ulaw_bate_certo_com_a_referencia_em_todos_os_256_valores():
    audioop = pytest.importorskip("audioop")  # removido no Python 3.13: o teste acima cobre esse caso
    for b in range(256):
        assert _amostra(b) == struct.unpack("<h", audioop.ulaw2lin(bytes([b]), 2))[0], hex(b)


def test_silencio_e_ruido_de_linha_nao_sao_fala():
    assert not stt.tem_fala(b"\xff" * 16000)            # zero puro
    assert not stt.tem_fala(b"\xfe\x7e" * 8000)         # ±8: ruído de linha
    assert not stt.tem_fala(b"")


def test_sinal_forte_e_fala():
    assert stt.tem_fala(b"\x00\x80" * 8000)             # ±32124
    assert stt.tem_fala(b"\x90\x10" * 8000)             # ~±1000


@pytest.mark.parametrize("texto", ["Legendas pela comunidade Amara.org", "legendado por X", "Obrigado por assistir!"])
def test_alucinacoes_do_whisper_sao_filtradas(texto):
    assert stt.e_alucinacao(texto)


@pytest.mark.parametrize("texto", ["Chamada Telefónica", "Chamada telefónica.", "chamada telefónica em português de Portugal"])
def test_eco_do_inicio_do_prompt_e_alucinacao(texto):
    assert stt.e_alucinacao(texto)


@pytest.mark.parametrize("texto", ["Figueira da Foz", "Buarcos e Quiaios", "T2", "Chamada", "Procuro um T2", "euros, mil euros"])
def test_vocabulario_do_prompt_e_resposta_legitima(texto):
    assert not stt.e_alucinacao(texto), "a zona dita a sós não é eco"


def test_texto_normal_nao_e_filtrado():
    assert not stt.e_alucinacao("Bom dia, procuro um T2 na Figueira da Foz")


def test_transcribe_nao_chama_o_whisper_com_silencio(monkeypatch):
    class _Nunca:
        class audio:  # noqa: N801
            class transcriptions:  # noqa: N801
                @staticmethod
                async def create(**_):
                    raise AssertionError("não devia chamar o Whisper")
    monkeypatch.setattr(stt, "_client", _Nunca)
    assert asyncio.run(stt.transcribe(b"\xff" * 16000)) == ""


def test_transcribe_descarta_alucinacao(monkeypatch):
    class _R:
        text = " Legendas pela comunidade Amara.org "

    class _Cli:
        class audio:  # noqa: N801
            class transcriptions:  # noqa: N801
                @staticmethod
                async def create(**_):
                    return _R()
    monkeypatch.setattr(stt, "_client", _Cli)
    assert asyncio.run(stt.transcribe(b"\x00\x80" * 8000)) == ""


def _pcm(*valores):
    return struct.pack(f"<{len(valores)}h", *valores)


def _pico(pcm):
    return max(abs(v) for (v,) in struct.iter_unpack("<h", pcm))


def test_normalizar_sobe_voz_fraca_ate_ao_pico_alvo_sem_saturar():
    assert _pico(stt._normalizar(_pcm(3000, -3000))) == 12000, "ganho máximo de 4× (+12 dB)"
    assert _pico(stt._normalizar(_pcm(15000, -15000))) == 22000, "ao pico alvo"
    assert _pico(stt._normalizar(_pcm(32000, -32000))) == 32000, "já alto: não se mexe"


def test_normalizar_nao_levanta_ruido_nem_silencio():
    assert stt._normalizar(_pcm(100, -100, 50)) == _pcm(100, -100, 50), "abaixo de 300 não há sinal"
    assert stt._normalizar(b"") == b""


def test_transcribe_usa_o_modelo_configurado_e_o_vocabulario(monkeypatch):
    visto = {}

    class _R:
        text = "quero um T2"

    class _Cli:
        class audio:  # noqa: N801
            class transcriptions:  # noqa: N801
                @staticmethod
                async def create(**kw):
                    visto.update(kw)
                    return _R()
    monkeypatch.setattr(stt, "_client", _Cli)
    monkeypatch.setattr(settings, "stt_model", "gpt-4o-mini-transcribe")
    assert asyncio.run(stt.transcribe(bytes([0x00, 0x80]) * 8000)) == "quero um T2"
    assert visto["model"] == "gpt-4o-mini-transcribe" and visto["language"] == "pt"
    assert "T2" in visto["prompt"] and "Figueira da Foz" in visto["prompt"]


class _Resposta:
    def __init__(self, text):
        self.text = text


def _cliente_por_modelo(textos, chamadas, rebenta=()):
    class _Cli:
        class audio:  # noqa: N801
            class transcriptions:  # noqa: N801
                @staticmethod
                async def create(**kw):
                    chamadas.append(kw["model"])
                    if kw["model"] in rebenta:
                        raise RuntimeError("parâmetro não suportado")
                    return _Resposta(textos[kw["model"]])
    return _Cli


def _corre_com_comparacao(monkeypatch, comparar, textos, rebenta=()):
    import logging
    chamadas, linhas = [], []

    class _H(logging.Handler):
        def emit(self, rec):
            linhas.append(rec.getMessage())

    log = logging.getLogger("app.agents.voice.stt")
    h = _H()
    log.addHandler(h)
    monkeypatch.setattr(stt, "_client", _cliente_por_modelo(textos, chamadas, rebenta))
    monkeypatch.setattr(settings, "stt_model", "gpt-4o-transcribe")
    monkeypatch.setattr(settings, "stt_comparar", comparar)

    async def _run():
        texto = await stt.transcribe(bytes([0x00, 0x80]) * 8000)
        await asyncio.gather(*stt._comparacoes)  # a comparação corre em segundo plano
        return texto

    try:
        return asyncio.run(_run()), chamadas, linhas
    finally:
        log.removeHandler(h)


def test_texto_vazio_ou_filtrado_deixa_o_bruto_no_log(monkeypatch):
    """Antes só se via o que sobrava do filtro, e não se sabia se o modelo devolvera vazio ou se o filtro o cortara."""
    for devolve, esperado in (("", "vazio"), ("Chamada Telefónica", "descartado")):
        _, _, linhas = _corre_com_comparacao(monkeypatch, "", {"gpt-4o-transcribe": devolve})
        assert any("STT bruto" in l and esperado in l for l in linhas), (devolve, linhas)
    _, _, linhas = _corre_com_comparacao(monkeypatch, "", {"gpt-4o-transcribe": "um T2"})
    assert not any("STT bruto" in l for l in linhas), "texto normal não polui o log"


def _wav_info(wav: bytes):
    import io
    import wave
    with wave.open(io.BytesIO(wav), "rb") as w:
        return w.getframerate(), w.getnframes(), w.readframes(w.getnframes())


def test_wav_reforcado_e_16k_com_300_ms_de_margem_e_o_sinal_intacto():
    pcmu = bytes([0x90, 0x10]) * 400  # 800 amostras a 8 kHz = 100 ms
    taxa, n, dados = _wav_info(stt._to_wav(pcmu, reforcado=True))
    assert taxa == 16000 and n == 2 * 800 + 2 * 4800, "2× as amostras + 300 ms de margem em cada ponta"
    margem = 4800 * 2
    assert dados[:margem] == bytes(margem) and dados[-margem:] == bytes(margem), "as margens são silêncio"
    assert any(dados[margem:-margem]), "o sinal está lá"
    taxa0, n0, _ = _wav_info(stt._to_wav(pcmu))
    assert (taxa0, n0) == (8000, 800), "sem reforço, o áudio é o de antes"


def _cliente_sequencia(respostas, chamadas):
    class _Cli:
        class audio:  # noqa: N801
            class transcriptions:  # noqa: N801
                @staticmethod
                async def create(**kw):
                    chamadas.append({"prompt": "prompt" in kw, "taxa": _wav_info(kw["file"].getvalue())[0]})
                    return _Resposta(respostas.pop(0))
    return _Cli


def test_resposta_vazia_tem_2_tentativa_a_16k_sem_prompt(monkeypatch):
    """18-19/10: «sim» e nomes curtos chegavam vazios e a conversa encravava."""
    chamadas = []
    monkeypatch.setattr(stt, "_client", _cliente_sequencia(["", "João Marques."], chamadas))
    monkeypatch.setattr(settings, "stt_comparar", "")
    texto = asyncio.run(stt.transcribe(bytes([0x00, 0x80]) * 8000))
    assert texto == "João Marques."
    assert chamadas == [{"prompt": True, "taxa": 8000}, {"prompt": False, "taxa": 16000}]


def test_texto_normal_nao_gasta_2_tentativa(monkeypatch):
    chamadas = []
    monkeypatch.setattr(stt, "_client", _cliente_sequencia(["Sim."], chamadas))
    monkeypatch.setattr(settings, "stt_comparar", "")
    assert asyncio.run(stt.transcribe(bytes([0x00, 0x80]) * 8000)) == "Sim." and len(chamadas) == 1


def test_duas_tentativas_vazias_continuam_vazias(monkeypatch):
    chamadas = []
    monkeypatch.setattr(stt, "_client", _cliente_sequencia(["", ""], chamadas))
    monkeypatch.setattr(settings, "stt_comparar", "")
    assert asyncio.run(stt.transcribe(bytes([0x00, 0x80]) * 8000)) == "" and len(chamadas) == 2


def test_comparacao_desligada_so_chama_o_modelo_principal(monkeypatch):
    texto, chamadas, linhas = _corre_com_comparacao(monkeypatch, "", {"gpt-4o-transcribe": "um T2"})
    assert texto == "um T2" and chamadas == ["gpt-4o-transcribe"] and linhas == []


def test_comparacao_ligada_escreve_o_texto_de_cada_modelo_no_log(monkeypatch):
    textos = {"gpt-4o-transcribe": "um T2", "gpt-transcribe": "um T dois", "whisper-1": "1P2"}
    texto, chamadas, linhas = _corre_com_comparacao(monkeypatch, "gpt-transcribe, whisper-1", textos)
    assert texto == "um T2", "a resposta à chamada é sempre a do modelo principal"
    assert sorted(chamadas) == ["gpt-4o-transcribe", "gpt-transcribe", "whisper-1"]
    assert len(linhas) == 1 and all(t in linhas[0] for t in ("'um T2'", "'um T dois'", "'1P2'", "whisper-1"))


def test_modelo_que_rebenta_na_comparacao_nao_estraga_a_chamada(monkeypatch):
    textos = {"gpt-4o-transcribe": "um T2", "whisper-1": "1P2"}
    texto, _, linhas = _corre_com_comparacao(monkeypatch, "gpt-transcribe,whisper-1", textos, rebenta=("gpt-transcribe",))
    assert texto == "um T2"
    assert "gpt-transcribe: ERRO RuntimeError" in linhas[0] and "'1P2'" in linhas[0]


def test_o_principal_nao_se_repete_na_comparacao(monkeypatch):
    _, chamadas, _ = _corre_com_comparacao(monkeypatch, "gpt-4o-transcribe", {"gpt-4o-transcribe": "um T2"})
    assert chamadas == ["gpt-4o-transcribe"]


def test_saudacao_apresenta_a_ia_avisa_da_transcricao_e_nao_e_gendrada():
    from app.agents.voice import claude_agent
    s = claude_agent.SAUDACAO
    assert "assistente virtual" in s and "transcrita" in s and "Figueira Home" in s
    assert "ajudá-lo" not in s and "Figueirahome" not in s


def test_prompt_do_modelo_usa_a_mesma_saudacao_do_webhook():
    from app.agents.voice import claude_agent
    assert claude_agent.SAUDACAO in claude_agent._SYSTEM_BASE
    assert "{SAUDACAO}" not in claude_agent._SYSTEM_BASE, "f-string resolvida"
    assert webhook.SAUDACAO is claude_agent.SAUDACAO


def test_atender_diz_a_saudacao_nova(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    ditas = []

    async def _stream(_id):
        return None

    async def _speak(_id, texto):
        ditas.append(texto)

    monkeypatch.setattr(webhook.telnyx_api, "stream_start", _stream)
    monkeypatch.setattr(webhook.telnyx_api, "speak", _speak)
    session_mgr.create_session("c-saud", "+351912345678")
    app = FastAPI()
    app.include_router(webhook.router)
    corpo = {"data": {"event_type": "call.answered", "payload": {"call_control_id": "c-saud"}}}
    TestClient(app).post("/webhook/telnyx", json=corpo)
    session_mgr.remove_session("c-saud")
    assert ditas == [webhook.SAUDACAO]


def test_saudacao_marca_is_speaking_antes_de_falar(monkeypatch):
    """Sem isto o silêncio durante a saudação ia ao Whisper e a assistente respondia a ruído."""
    monkeypatch.setattr(settings, "environment", "development")
    visto = {}

    async def _stream(_id):
        return None

    async def _speak(call_id, _texto):
        visto["is_speaking"] = session_mgr.get_session(call_id).is_speaking

    monkeypatch.setattr(webhook.telnyx_api, "stream_start", _stream)
    monkeypatch.setattr(webhook.telnyx_api, "speak", _speak)
    session_mgr.create_session("c-teste", "+351912345678")
    app = FastAPI()
    app.include_router(webhook.router)
    corpo = {"data": {"event_type": "call.answered", "payload": {"call_control_id": "c-teste"}}}
    assert TestClient(app).post("/webhook/telnyx", json=corpo).status_code == 200
    assert visto == {"is_speaking": True}
    session_mgr.remove_session("c-teste")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
