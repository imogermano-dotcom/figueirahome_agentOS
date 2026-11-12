"""Lead já no eGO que responde e qualifica: avisa-se a consultora, sem tarefa `lead_ego` pendente (12/11).

Telefones de teste: `912345678`. Sem rede. Corre com `pytest backend/tests/`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker import guards  # noqa: E402

CLIENTE = {"id": "cl1", "nome": "Ana", "telefone": "912345678", "email": None,
           "tipo_interesse": "arrendamento", "orcamento": 500, "zona_preferida": "Figueira da Foz"}


class _BD:
    """`leads` devolve uma lead contactada, `contactos` as linhas dadas, `agente_tarefas` nada (nunca avisada)."""

    def __init__(self, contactos):
        self.contactos, self.tarefas, self._t = contactos, [], None

    def table(self, nome):
        self._t, self._ins = nome, None
        return self

    def __getattr__(self, nome):
        return self if nome == "not_" else (lambda *a, **k: self)

    def insert(self, valores):
        self._ins = valores
        return self

    def execute(self):
        if self._ins is not None:
            self.tarefas.append(self._ins)
            return type("R", (), {"data": [self._ins]})()
        dados = {"leads": [{"id": "l1", "estado": "contactada", "cliente_id": None, "imovel_ref": "FH0001",
                            "tipo": "compra", "origem": "meta"}],
                 "contactos": self.contactos}.get(self._t, [])
        return type("R", (), {"data": dados})()


def _corre(monkeypatch, contactos):
    avisos = []
    monkeypatch.setattr(guards, "notificar", lambda assunto, corpo, **k: avisos.append((assunto, corpo, k)))
    monkeypatch.setattr(guards, "marcar_interesse_real", lambda *a: False)
    bd = _BD(contactos)
    guards._promover_lead(bd, dict(CLIENTE))
    return bd, avisos


def test_lead_ja_no_ego_avisa_a_consultora_sem_tarefa_pendente(monkeypatch):
    bd, avisos = _corre(monkeypatch, [{"id": "c1"}])
    assert [t["tipo"] for t in bd.tarefas] == ["lead_ego_aviso"] and bd.tarefas[0]["estado"] == "concluida"
    assert len(avisos) == 1
    assunto, corpo, k = avisos[0]
    assert "já no eGO" in assunto and k["imovel_ref"] == "FH0001"
    assert "ARRENDAR" in corpo and "sem resposta" in corpo


def test_lead_fora_do_ego_continua_a_criar_a_tarefa_lead_ego(monkeypatch):
    bd, avisos = _corre(monkeypatch, [])
    assert [t["tipo"] for t in bd.tarefas] == ["lead_ego"]
    assert len(avisos) == 1 and "já no eGO" not in avisos[0][0]
