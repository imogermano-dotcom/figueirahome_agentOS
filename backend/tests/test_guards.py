"""Guardas de negócio — funções puras, sem DB nem rede.

Corre com `pytest backend/tests/` ou directamente com
`python backend/tests/test_guards.py`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker.guards import (  # noqa: E402
    _compativel,
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


def test_compativel_preenche_dados_em_falta():
    """O bug de 2026-08-03: nome gravado sem telefone, telefone chega depois.

    `guardar_dados_cliente` grava o nome (o modelo nem sempre passa o
    telefone); no turno seguinte `agendar_visita` traz o telefone. Sem isto,
    a procura por telefone falhava e criava-se uma segunda linha.
    """
    existente = {"nome": "Carlos Mendes", "telefone": None, "email": None}
    assert _compativel(existente, "912777888", None) is True
    assert _compativel(existente, None, "c@x.pt") is True


def test_compativel_recusa_quando_ha_contradicao():
    """Dois homónimos com telefones diferentes são duas pessoas."""
    joao_a = {"nome": "João Silva", "telefone": "911111111", "email": None}
    assert _compativel(joao_a, "922222222", None) is False
    assert _compativel(joao_a, "911111111", None) is True
    # Formatos diferentes do MESMO número continuam compatíveis.
    assert _compativel({"nome": "X", "telefone": "351911111111"}, "911111111", None) is True

    com_email = {"nome": "Ana", "telefone": None, "email": "ana@x.pt"}
    assert _compativel(com_email, None, "outra@x.pt") is False
    assert _compativel(com_email, None, "ana@x.pt") is True


def test_compativel_sem_identificadores():
    """Nada a contradizer — o nome é o único dado que temos."""
    assert _compativel({"nome": "Ana", "telefone": None, "email": None}, None, None) is True


if __name__ == "__main__":
    for nome, fn in list(globals().items()):
        if nome.startswith("test_"):
            fn()
            print(f"  ok  {nome}")
    print("test_guards OK")
