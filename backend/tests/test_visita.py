"""`agendar_visita` — desfecho "Interesse real" da spec §2.2.

A tarefa em `agente_tarefas` já existia; o que faltava era o aviso por email.
Era a única escrita cliente-facing sem `notificar` — e é a que mais o merece:
a pessoa está a pedir para ver a casa.

Corre com `pytest backend/tests/` ou directamente com
`python backend/tests/test_visita.py`.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.agents.broker.tools as tools  # noqa: E402

IMOVEL = {
    "imovel_ref": "FH2572",
    "venda_preco": 300000,
    "morada": "Rua das Acácias, Buarcos",
}

CONTEXTO = {"canal": "whatsapp", "telefone": "912345678", "agente": "a1_vendedor"}


@pytest.fixture
def visita(monkeypatch):
    """`tools` sem DB nem rede. Devolve `(marcar, registo)`."""
    registo = {"avisos": [], "tarefas": []}

    monkeypatch.setattr(tools, "_preco_do_imovel", lambda ref: dict(IMOVEL))
    monkeypatch.setattr(tools, "_inserir_tarefa", registo["tarefas"].append)
    monkeypatch.setattr(
        tools, "notificar",
        lambda assunto, corpo, imovel_ref=None: registo["avisos"].append(
            (assunto, corpo, imovel_ref)
        ),
    )

    async def _sem_cliente(**kwargs):
        return None

    monkeypatch.setattr(tools, "find_or_create_cliente", _sem_cliente)

    def marcar(**extra):
        inputs = {
            "imovel_ref": "FH2572",
            "nome": "Ana Luísa",
            "telefone": "912345678",
            "quando": "quinta às 15h",
            "orcamento": 280000,
            **extra,
        }
        return asyncio.run(tools._agendar_visita(inputs, CONTEXTO))

    return marcar, registo


def test_visita_marcada_avisa_o_consultor(visita):
    """Sem isto o pedido de visita fica numa linha do painel e depende de alguém
    o abrir — o mesmo buraco que `escalar_para_humano` já tinha fechado."""
    marcar, registo = visita

    marcar()

    assert len(registo["tarefas"]) == 1
    assert len(registo["avisos"]) == 1

    assunto, corpo, imovel_ref = registo["avisos"][0]
    # O `imovel_ref` é o que resolve a consultora que angariou o imóvel
    # (`notificacoes._consultor_do_imovel`); sem ele o aviso só vai ao director.
    assert imovel_ref == "FH2572"
    assert "FH2572" in assunto
    assert "912345678" in corpo
    assert "quinta às 15h" in corpo


def test_visita_recusada_pelos_80_por_cento_nao_avisa(visita):
    """A regra dos 80% recusa antes de qualquer escrita. Se o aviso saísse na
    mesma, o corretor recebia email de visitas que nunca foram marcadas."""
    marcar, registo = visita

    resposta = marcar(orcamento=100000)

    assert resposta.startswith("NÃO MARCADA")
    assert not registo["tarefas"]
    assert not registo["avisos"]


def test_visita_sem_orcamento_nao_avisa(visita):
    """Sem orçamento declarado a regra também recusa — e continua a não haver
    nada para avisar."""
    marcar, registo = visita

    resposta = marcar(orcamento=None)

    assert resposta.startswith("NÃO MARCADA")
    assert not registo["avisos"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
