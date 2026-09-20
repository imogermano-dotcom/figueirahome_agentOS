"""`escalar_para_humano` — dedup de tarefa/email dentro da mesma conversa.

Corre com `pytest backend/tests/` ou directamente com
`python backend/tests/test_escalar.py`.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.agents.broker.tools as tools  # noqa: E402

CONTEXTO = {"canal": "whatsapp", "telefone": "912345678", "agente": "a3_recrutamento", "conversa_id": "conv-1"}


@pytest.fixture
def escalar(monkeypatch):
    registo = {"avisos": [], "tarefas": []}

    monkeypatch.setattr(tools, "_inserir_tarefa", registo["tarefas"].append)
    monkeypatch.setattr(
        tools, "notificar",
        lambda assunto, corpo, imovel_ref=None: registo["avisos"].append((assunto, corpo, imovel_ref)),
    )

    async def _sem_cliente(**kwargs):
        return None

    monkeypatch.setattr(tools, "find_or_create_cliente", _sem_cliente)

    def chamar(**extra):
        inputs = {"nome": "Ana Luísa", "telefone": "912345678", "motivo": "entrevista de recrutamento", **extra}
        return asyncio.run(tools._escalar_para_humano(inputs, CONTEXTO))

    return chamar, registo


def test_escalar_cria_tarefa_e_avisa(escalar, monkeypatch):
    monkeypatch.setattr(tools, "_tarefa_ja_registada", lambda *a: False)
    chamar, registo = escalar

    chamar()

    assert len(registo["tarefas"]) == 1
    assert len(registo["avisos"]) == 1


def test_escalar_ja_registado_nao_duplica(escalar, monkeypatch):
    """Bug real (20/09, achado a testar a Inês): o modelo repete
    `escalar_para_humano` na mesma conversa ao confirmar de novo ao cliente
    — duas tarefas e dois emails, o mesmo motivo, segundos à parte."""
    monkeypatch.setattr(tools, "_tarefa_ja_registada", lambda *a: True)
    chamar, registo = escalar

    resposta = chamar()

    assert "já está registado" in resposta.lower()
    assert not registo["tarefas"]
    assert not registo["avisos"]


def test_escalar_motivo_diferente_nao_e_bloqueado(escalar, monkeypatch):
    """A dedup é por (conversa, tipo, motivo) — um pedido genuinamente
    diferente na mesma conversa continua a passar."""
    chamado_com = []
    monkeypatch.setattr(
        tools, "_tarefa_ja_registada",
        lambda conversa_id, tipo, coluna, valor: chamado_com.append(valor) or valor == "entrevista de recrutamento",
    )
    chamar, registo = escalar

    resposta = chamar(motivo="dúvida sobre licença AMI")

    assert "já está registado" not in resposta.lower()
    assert len(registo["tarefas"]) == 1
    assert chamado_com == ["dúvida sobre licença AMI"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
