"""`/api/broker/chat` ficou anos sem `require_auth`, apesar de todos os outros
endpoints do painel o terem, e aceitava `agente` escolhido pelo próprio pedido
-- ou seja, um chamador não autenticado podia pedir `agente=\"broker\"` e falar
directamente com o assistente que lê `consultar_clientes`/`consultar_leads`.
Achado e corrigido a 2026-08-31."""

from fastapi.testclient import TestClient

from app.main import app


def test_broker_chat_exige_autenticacao():
    r = TestClient(app).post("/api/broker/chat", json={"mensagem": "ola"})
    assert r.status_code == 401


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
