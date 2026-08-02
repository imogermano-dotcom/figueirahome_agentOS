"""Guardas de negócio — funções puras, sem DB nem rede.

Corre com `pytest backend/tests/` ou directamente com
`python backend/tests/test_guards.py`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker.guards import (  # noqa: E402
    normalizar_email,
    normalizar_telefone,
    visita_permitida,
)


def test_normalizar_telefone():
    # Mesmo número, quatro formatos vistos em produção (Meta, cliente, painel).
    assert normalizar_telefone("+351 912 345-678") == "912345678"
    assert normalizar_telefone("00351912345678") == "912345678"
    assert normalizar_telefone("351912345678") == "912345678"
    assert normalizar_telefone("912345678") == "912345678"
    assert normalizar_telefone("") is None
    assert normalizar_telefone(None) is None


def test_normalizar_email():
    assert normalizar_email("  A@B.COM ") == "a@b.com"
    assert normalizar_email("") is None
    assert normalizar_email(None) is None


def test_visita_permitida():
    # Spec §3.2: €240k sobre €300k é o limiar exacto e avança.
    assert visita_permitida(240000, 300000) is True
    assert visita_permitida(300000, 300000) is True
    assert visita_permitida(239999, 300000) is False
    assert visita_permitida(200000, 300000) is False


def test_visita_permitida_sem_dados():
    assert visita_permitida(None, 300000) is False  # spec 3c: insistir, não marcar
    assert visita_permitida(100000, None) is False  # sem preço, sem divisão por zero
    assert visita_permitida(100000, 0) is False


if __name__ == "__main__":
    test_normalizar_telefone()
    test_normalizar_email()
    test_visita_permitida()
    test_visita_permitida_sem_dados()
    print("test_guards OK")
