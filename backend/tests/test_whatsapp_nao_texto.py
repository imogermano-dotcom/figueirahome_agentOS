"""Mensagens de WhatsApp que não são texto (pedido #10, 26/10): áudio, imagem e ficheiros ficavam sem resposta nenhuma.

Agora respondem-se uma vez («escreva, por favor»), as legendas e as respostas a botões contam como texto, e fica registado.
Sem rede. Corre com `pytest backend/tests/`.
"""

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker.channels.whatsapp import webhook  # noqa: E402
from app.config import settings  # noqa: E402


# ── que texto tem a mensagem ──────────────────────────────────────────────

@pytest.mark.parametrize("msg,texto", [
    ({"type": "text", "text": {"body": "Olá"}}, "Olá"),
    ({"type": "image", "image": {"caption": " Esta é a casa "}}, "Esta é a casa"),
    ({"type": "document", "document": {"caption": "contrato"}}, "contrato"),
    ({"type": "video", "video": {"caption": "vídeo"}}, "vídeo"),
    ({"type": "button", "button": {"text": "Sim, quero"}}, "Sim, quero"),
    ({"type": "interactive", "interactive": {"button_reply": {"title": "Comprar"}}}, "Comprar"),
    ({"type": "interactive", "interactive": {"list_reply": {"title": "Arrendar"}}}, "Arrendar"),
    ({"type": "image", "image": {}}, ""),
    ({"type": "audio", "audio": {"voice": True}}, ""),
    ({"type": "sticker"}, ""),
    ({"type": "reaction", "reaction": {"emoji": "👍"}}, ""),
    ({"type": "interactive", "interactive": {"nfm_reply": {}}}, ""),
    ({}, ""),
])
def test_texto_da_mensagem(msg, texto):
    assert webhook._texto_da_mensagem(msg) == texto


# ── o aviso ───────────────────────────────────────────────────────────────

@pytest.fixture
def mundo(monkeypatch):
    estado = {"enviados": [], "lidas": [], "logs": []}

    async def _enviar(para, texto, phone_number_id=None):
        estado["enviados"].append((para, texto))

    async def _ler(message_id, phone_number_id=None):
        estado["lidas"].append(message_id)

    class _Tabela:
        def insert(self, dados):
            estado["logs"].append(dados)
            return self

        def execute(self):
            return self

    monkeypatch.setattr(webhook, "send_text_message", _enviar)
    monkeypatch.setattr(webhook, "mark_as_read", _ler)
    monkeypatch.setattr(webhook, "_ja_processada", lambda _id: estado.get("repetida", False))
    monkeypatch.setattr(webhook, "get_supabase", lambda: type("S", (), {"table": lambda self, n: _Tabela()})())
    webhook._ultimo_aviso.clear()
    return estado


def test_audio_recebe_o_aviso_de_voz(mundo):
    asyncio.run(webhook._avisar_que_so_le_texto("351900000001", "m1", "audio"))
    assert mundo["enviados"] == [("351900000001", webhook._AVISO_AUDIO)] and "voz" in webhook._AVISO_AUDIO
    assert mundo["lidas"] == ["m1"]


def test_imagem_recebe_o_aviso_generico(mundo):
    asyncio.run(webhook._avisar_que_so_le_texto("351900000001", "m1", "image"))
    assert mundo["enviados"] == [("351900000001", webhook._AVISO_OUTRO)]


def test_cinco_fotografias_seguidas_dao_uma_resposta(mundo):
    for i in range(5):
        asyncio.run(webhook._avisar_que_so_le_texto("351900000001", f"m{i}", "image"))
    assert len(mundo["enviados"]) == 1


def test_pessoas_diferentes_recebem_cada_uma_o_seu(mundo):
    asyncio.run(webhook._avisar_que_so_le_texto("351900000001", "m1", "image"))
    asyncio.run(webhook._avisar_que_so_le_texto("351900000002", "m2", "audio"))
    assert [p for p, _ in mundo["enviados"]] == ["351900000001", "351900000002"]


def test_reentrega_da_meta_nao_responde_outra_vez(mundo):
    mundo["repetida"] = True
    asyncio.run(webhook._avisar_que_so_le_texto("351900000001", "m1", "audio"))
    assert mundo["enviados"] == []


def test_fica_registado_so_com_os_3_ultimos_digitos(mundo):
    asyncio.run(webhook._avisar_que_so_le_texto("351912345678", "m1", "audio"))
    (log,) = mundo["logs"]
    assert log["tipo"] == "whatsapp_nao_texto" and log["resumo"] == {"tipo": "audio", "participante": "…678"}


def test_falha_a_enviar_nao_levanta(mundo, monkeypatch):
    async def _rebenta(*a, **k):
        raise RuntimeError("Meta em baixo")

    monkeypatch.setattr(webhook, "send_text_message", _rebenta)
    asyncio.run(webhook._avisar_que_so_le_texto("351900000001", "m1", "audio"))


# ── o webhook ─────────────────────────────────────────────────────────────

def _post(monkeypatch, mensagem):
    chamadas = {"texto": [], "aviso": []}

    async def _texto(from_number, message_id, text, phone_number_id=None):
        chamadas["texto"].append((from_number, text))

    async def _aviso(from_number, message_id, tipo, phone_number_id=None):
        chamadas["aviso"].append((from_number, tipo))

    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(webhook, "_handle_message", _texto)
    monkeypatch.setattr(webhook, "_avisar_que_so_le_texto", _aviso)
    monkeypatch.setattr(webhook.recibos, "limpar_falha", lambda *a, **k: None)
    app = FastAPI()
    app.include_router(webhook.router)
    payload = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "1"},
                                                 "messages": [{"from": "351900000001", "id": "m1"} | mensagem]}}]}]}
    assert TestClient(app).post("/webhook/whatsapp", json=payload).status_code == 200
    return chamadas


def test_webhook_audio_vai_para_o_aviso_e_nao_para_o_motor(monkeypatch):
    assert _post(monkeypatch, {"type": "audio", "audio": {}}) == {"texto": [], "aviso": [("351900000001", "audio")]}


def test_webhook_imagem_com_legenda_e_texto(monkeypatch):
    assert _post(monkeypatch, {"type": "image", "image": {"caption": "Quanto custa?"}}) == {"texto": [("351900000001", "Quanto custa?")], "aviso": []}


def test_webhook_texto_continua_igual(monkeypatch):
    assert _post(monkeypatch, {"type": "text", "text": {"body": "Olá"}}) == {"texto": [("351900000001", "Olá")], "aviso": []}


@pytest.mark.parametrize("tipo", ["reaction", "sticker", "system", "unsupported"])
def test_reacoes_e_stickers_continuam_ignorados(monkeypatch, tipo):
    assert _post(monkeypatch, {"type": tipo}) == {"texto": [], "aviso": []}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
