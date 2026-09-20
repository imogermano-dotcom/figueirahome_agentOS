"""`pedir_visita` — desfecho "Interesse real" da spec §2.2.

O A1 não agenda horário (17/09): regista o pedido, garante lead e avisa por
email — quem marca é a consultora, por contacto directo. A tarefa em
`agente_tarefas` já existia; o que faltava era o aviso por email E a lead —
era a única escrita cliente-facing sem `notificar`, e o único caminho de
`_criar_lead_se_preciso` que nunca era chamado (cliente ficava gravado, lead
nenhuma — bug real, achado a analisar conversas em produção).

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
    """`tools` sem DB nem rede. Devolve `(pedir, registo)`."""
    registo = {"avisos": [], "tarefas": [], "leads": []}

    monkeypatch.setattr(tools, "_preco_do_imovel", lambda ref: dict(IMOVEL))
    monkeypatch.setattr(tools, "_inserir_tarefa", registo["tarefas"].append)
    monkeypatch.setattr(
        tools, "notificar",
        lambda assunto, corpo, imovel_ref=None: registo["avisos"].append(
            (assunto, corpo, imovel_ref)
        ),
    )
    monkeypatch.setattr(
        tools, "_criar_lead_se_preciso",
        lambda cliente, resumo: registo["leads"].append((cliente, resumo)),
    )
    monkeypatch.setattr(tools, "_tarefa_ja_registada", lambda *a: False)

    async def _sem_cliente(**kwargs):
        return None

    monkeypatch.setattr(tools, "find_or_create_cliente", _sem_cliente)

    def pedir(**extra):
        inputs = {
            "imovel_ref": "FH2572",
            "nome": "Ana Luísa",
            "telefone": "912345678",
            "quando": "quinta à tarde",
            "orcamento": 280000,
            **extra,
        }
        return asyncio.run(tools._pedir_visita(inputs, CONTEXTO))

    return pedir, registo


def test_visita_pedida_avisa_o_consultor(visita):
    """Sem isto o pedido de visita fica numa linha do painel e depende de alguém
    o abrir — o mesmo buraco que `escalar_para_humano` já tinha fechado."""
    pedir, registo = visita

    pedir()

    assert len(registo["tarefas"]) == 1
    assert len(registo["avisos"]) == 1

    assunto, corpo, imovel_ref = registo["avisos"][0]
    # O `imovel_ref` é o que resolve a consultora que angariou o imóvel
    # (`notificacoes._consultor_do_imovel`); sem ele o aviso só vai ao director.
    assert imovel_ref == "FH2572"
    assert "FH2572" in assunto
    assert "912345678" in corpo
    assert "quinta à tarde" in corpo


def test_visita_pedida_garante_lead(visita, monkeypatch):
    """Buraco real (17/09): `_pedir_visita` criava cliente mas nunca lead —
    só `guardar_dados_cliente` chamava `_criar_lead_se_preciso`, e uma
    conversa podia pedir visita sem alguma vez passar por lá."""
    pedir, registo = visita

    async def _com_cliente(**kwargs):
        return {"id": "cliente-1", "telefone": "912345678"}

    monkeypatch.setattr(tools, "find_or_create_cliente", _com_cliente)

    pedir()

    assert len(registo["leads"]) == 1
    cliente, resumo = registo["leads"][0]
    assert cliente["id"] == "cliente-1"
    assert "FH2572" in resumo


def test_visita_ja_registada_nao_duplica(visita, monkeypatch):
    """Bug real (20/09): o modelo repete `pedir_visita` na mesma conversa ao
    confirmar de novo ao cliente — tool_use/tool_result não ficam guardados
    entre turnos, só o texto final. Sem dedup, duas tarefas e dois emails."""
    pedir, registo = visita
    monkeypatch.setattr(tools, "_tarefa_ja_registada", lambda *a: True)

    resposta = pedir()

    assert "já está registado" in resposta.lower()
    assert not registo["tarefas"]
    assert not registo["avisos"]
    assert not registo["leads"]


def test_visita_recusada_pelos_80_por_cento_nao_avisa(visita):
    """A regra dos 80% recusa antes de qualquer escrita. Se o aviso saísse na
    mesma, o corretor recebia email de visitas que nunca foram pedidas."""
    pedir, registo = visita

    resposta = pedir(orcamento=100000)

    assert resposta.startswith("NÃO REGISTADO")
    assert not registo["tarefas"]
    assert not registo["avisos"]
    assert not registo["leads"]


def test_visita_sem_orcamento_nao_avisa(visita):
    """Sem orçamento declarado a regra também recusa — e continua a não haver
    nada para avisar."""
    pedir, registo = visita

    resposta = pedir(orcamento=None)

    assert resposta.startswith("NÃO REGISTADO")
    assert not registo["avisos"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
