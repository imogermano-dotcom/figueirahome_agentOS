"""`send_text_message` — o payload que sai para a Cloud API.

Uma coisa só, e é a que falhou ao vivo: **`preview_url` é `false` por omissão**
na Cloud API. Sem a chave o WhatsApp mostra o endereço em texto cru e nem sequer
vai buscar as OG tags — ao contrário do WhatsApp normal, onde a pré-visualização
é automática. A 2026-08-25 a Matilde mandava o link da landing page e chegava
sem cartão nenhum.

Falha em silêncio: a API devolve 200, a mensagem chega, e só se dá por isso a
olhar para o telemóvel. Por isso tem teste.

Corre com `pytest backend/tests/` ou directamente com
`python backend/tests/test_meta_api.py`.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.agents.broker.channels.whatsapp.meta_api as meta  # noqa: E402


@pytest.fixture
def enviados(monkeypatch):
    """Substitui o `httpx.AsyncClient` e devolve a lista de payloads enviados."""
    payloads = []

    class _Resp:
        status_code = 200
        text = ""

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            payloads.append(json)
            return _Resp()

    monkeypatch.setattr(meta.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setattr(meta, "para_whatsapp", lambda t: t)
    return payloads


def test_preview_url_vai_sempre(enviados):
    asyncio.run(meta.send_text_message("351912345678", "Aqui está: https://imoveis.figueirahome.pt/FH2571"))

    assert len(enviados) == 1
    # A chave tem de existir E ser True — ausente vale `false` na Cloud API.
    assert enviados[0]["text"]["preview_url"] is True
    assert "https://imoveis.figueirahome.pt/FH2571" in enviados[0]["text"]["body"]


def test_mensagem_longa_parte_em_pedacos_todos_com_preview(enviados):
    asyncio.run(meta.send_text_message("351912345678", "x" * (meta._MAX_MESSAGE_LENGTH + 10)))

    assert len(enviados) == 2, "parte ao chegar ao limite"
    assert all(p["text"]["preview_url"] is True for p in enviados)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
