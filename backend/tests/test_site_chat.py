"""`/api/site/chat` é o único endpoint 100% público, sem `require_auth` nem
segredo -- ver `docs/fases/webchat-site-plano.md`. Dois riscos cobertos:

1. Um `agente` vindo do pedido reabriria o furo corrigido em `api/broker.py`
   a 2026-08-31 (agente="broker" não autenticado lia consultar_clientes).
2. Sem limite de tamanho/frequência, tráfego avulso esgota crédito da API
   Anthropic à conta da agência.
"""

import app.api.site_chat as site_chat
from fastapi.testclient import TestClient

from app.main import app


def _mock_responder(monkeypatch, capturado):
    async def _fake(**kwargs):
        capturado.append(kwargs)
        return "resposta de teste"

    monkeypatch.setattr(site_chat, "responder", _fake)


def test_responde_e_usa_canal_site_sem_agente(monkeypatch):
    capturado = []
    _mock_responder(monkeypatch, capturado)

    r = TestClient(app).post(
        "/api/site/chat", json={"participante": "visitante-1", "mensagem": "ola"}
    )

    assert r.status_code == 200
    assert r.json() == {"resposta": "resposta de teste"}
    assert capturado[0]["canal"] == "site"
    assert "agente" not in capturado[0]


def test_campo_agente_no_pedido_e_ignorado(monkeypatch):
    """Mesmo que o schema um dia ganhe mais campos por engano, um `agente`
    à socapa no JSON não pode chegar ao `responder`."""
    capturado = []
    _mock_responder(monkeypatch, capturado)

    r = TestClient(app).post(
        "/api/site/chat",
        json={"participante": "visitante-1", "mensagem": "ola", "agente": "broker"},
    )

    assert r.status_code == 200
    assert "agente" not in capturado[0]


def test_mensagem_vazia_rejeitada(monkeypatch):
    _mock_responder(monkeypatch, [])
    r = TestClient(app).post(
        "/api/site/chat", json={"participante": "visitante-1", "mensagem": ""}
    )
    assert r.status_code == 422


def test_mensagem_demasiado_longa_rejeitada(monkeypatch):
    _mock_responder(monkeypatch, [])
    r = TestClient(app).post(
        "/api/site/chat",
        json={"participante": "visitante-1", "mensagem": "x" * 2001},
    )
    assert r.status_code == 422


def test_rate_limit_por_participante(monkeypatch):
    monkeypatch.setattr(site_chat, "_pedidos", {})
    _mock_responder(monkeypatch, [])
    client = TestClient(app)

    for _ in range(site_chat._MAX_PEDIDOS_NA_JANELA):
        r = client.post(
            "/api/site/chat", json={"participante": "spammer", "mensagem": "ola"}
        )
        assert r.status_code == 200

    r = client.post(
        "/api/site/chat", json={"participante": "spammer", "mensagem": "ola"}
    )
    assert r.status_code == 429


def test_rate_limit_e_por_participante_nao_global(monkeypatch):
    monkeypatch.setattr(site_chat, "_pedidos", {})
    _mock_responder(monkeypatch, [])
    client = TestClient(app)

    for _ in range(site_chat._MAX_PEDIDOS_NA_JANELA):
        client.post("/api/site/chat", json={"participante": "spammer", "mensagem": "ola"})

    r = client.post(
        "/api/site/chat", json={"participante": "outro-visitante", "mensagem": "ola"}
    )
    assert r.status_code == 200


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
