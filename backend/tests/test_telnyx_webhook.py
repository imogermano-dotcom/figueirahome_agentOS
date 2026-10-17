"""Verificação da assinatura do webhook da Telnyx (`app/agents/voice/webhook.py`).

Corre com `pytest backend/tests/` ou `python backend/tests/test_telnyx_webhook.py`.
As chaves são geradas aqui (Ed25519): nada de credenciais reais. Sem rede.
"""

import base64
import json
import sys
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.voice import webhook  # noqa: E402
from app.config import settings  # noqa: E402

AGORA = 1_760_000_000
CORPO = json.dumps({"data": {"event_type": "call.speak.ended", "payload": {"call_control_id": "c1"}}}).encode()


def _chave():
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return priv, base64.b64encode(pub).decode()


def _assina(priv, corpo=CORPO, ts=AGORA):
    return base64.b64encode(priv.sign(str(ts).encode() + b"|" + corpo)).decode()


def test_assinatura_valida_passa():
    priv, pub = _chave()
    assert webhook.assinatura_valida(CORPO, _assina(priv), str(AGORA), pub, agora=AGORA + 5)


def test_corpo_alterado_chave_errada_e_timestamp_velho_falham():
    priv, pub = _chave()
    _, outra = _chave()
    sig = _assina(priv)
    assert not webhook.assinatura_valida(CORPO + b" ", sig, str(AGORA), pub, agora=AGORA)
    assert not webhook.assinatura_valida(CORPO, sig, str(AGORA), outra, agora=AGORA)
    assert not webhook.assinatura_valida(CORPO, sig, str(AGORA), pub, agora=AGORA + 301), "replay depois de 5 min"
    assert not webhook.assinatura_valida(CORPO, sig, str(AGORA + 1), pub, agora=AGORA), "timestamp trocado"


@pytest.mark.parametrize("chave,sig,ts", [("", "x", "1"), ("não-base64!!", "x", "1"), ("QUJD", "", str(AGORA)),
                                          ("QUJD", "QUJD", "abc"), ("QUJD", "QUJD", "")])
def test_lixo_nunca_levanta_e_nunca_passa(chave, sig, ts):
    assert webhook.assinatura_valida(CORPO, sig, ts, chave, agora=AGORA) is False


def _cliente(monkeypatch, pub, ambiente="production"):
    monkeypatch.setattr(settings, "environment", ambiente)
    monkeypatch.setattr(settings, "telnyx_public_key", pub)
    app = FastAPI()
    app.include_router(webhook.router)
    return TestClient(app)


def test_endpoint_em_producao_recusa_sem_assinatura_e_com_chave_vazia(monkeypatch):
    _, pub = _chave()
    assert _cliente(monkeypatch, pub).post("/webhook/telnyx", content=CORPO).status_code == 403
    # Segredo em falta nunca abre o webhook (antes, sem chave, passava tudo).
    assert _cliente(monkeypatch, "").post("/webhook/telnyx", content=CORPO).status_code == 403


def test_endpoint_em_producao_aceita_assinatura_valida(monkeypatch):
    priv, pub = _chave()
    ts = int(time.time())
    r = _cliente(monkeypatch, pub).post(
        "/webhook/telnyx", content=CORPO,
        headers={"telnyx-signature-ed25519": _assina(priv, ts=ts), "telnyx-timestamp": str(ts)},
    )
    assert r.status_code == 200 and r.json() == {"result": "ok"}


def test_fora_de_producao_nao_verifica(monkeypatch):
    assert _cliente(monkeypatch, "", ambiente="development").post("/webhook/telnyx", content=CORPO).status_code == 200


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
