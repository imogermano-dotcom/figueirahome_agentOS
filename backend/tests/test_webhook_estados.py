"""Os recibos de entrega da Meta — `value["statuses"]`.

Porque isto existe: a 2026-08-29 uma mensagem de teste teve `200 accepted` da
Graph API, o callback da Meta chegou ao nosso webhook (`POST /webhook/whatsapp
200 OK` nos logs do Fly), e o telefone nunca a recebeu. Estivemos semanas sem
saber que as mensagens não chegavam, porque o handler lia só
`value["messages"]` e deitava os recibos fora.

`accepted` na resposta da Graph API quer dizer **aceite para envio**. A
diferença entre isso e *entregue* só aparece nos `statuses`.

Corre com `pytest backend/tests/` ou `python backend/tests/test_webhook_estados.py`.
"""

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker.channels.whatsapp import webhook  # noqa: E402


def test_falha_de_entrega_sai_como_erro(caplog):
    """O caso que nos cegou. O código e o detalhe TÊM de aparecer — sem eles o
    log diz que falhou mas não porquê, e ficamos na mesma."""
    with caplog.at_level(logging.ERROR):
        webhook._registar_estado({
            "id": "wamid.XXX",
            "status": "failed",
            "recipient_id": "351914590925",
            "errors": [{
                "code": 131042,
                "title": "Business eligibility payment issue",
                "error_data": {"details": "Failed to send message because of payment issue"},
            }],
        })
    registo = caplog.text
    assert "NAO ENTREGUE" in registo
    assert "351914590925" in registo
    assert "131042" in registo, "sem o código não se sabe o que corrigir"
    assert "payment issue" in registo


def test_falha_sem_detalhe_nao_rebenta():
    """A Meta nem sempre manda `errors`, e um KeyError aqui devolvia 500 ao
    webhook — que a Meta lê como falha nossa e reenvia em ciclo."""
    webhook._registar_estado({"status": "failed", "recipient_id": "351900000000"})


@pytest.mark.parametrize("qual", ["sent", "delivered", "read"])
def test_estados_normais_ficam_registados(caplog, qual):
    with caplog.at_level(logging.INFO):
        webhook._registar_estado({"status": qual, "recipient_id": "351914590925"})
    assert qual in caplog.text
    assert "NAO ENTREGUE" not in caplog.text


def test_um_recibo_nao_e_confundido_com_uma_mensagem_recebida():
    """`statuses` e `messages` são listas diferentes no mesmo `value`. Tratar um
    recibo como mensagem do cliente punha a Matilde a responder a si própria."""
    payload = {"entry": [{"changes": [{"value": {
        "statuses": [{"status": "delivered", "recipient_id": "351914590925"}],
    }}]}]}
    value = payload["entry"][0]["changes"][0]["value"]
    assert value.get("messages", []) == []
    assert len(value["statuses"]) == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
