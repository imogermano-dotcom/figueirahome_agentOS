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
    bd, avisos = _corre(monkeypatch, [{"id": "c1", "ego_lead_em": "2026-11-01T10:00:00+00:00", "meta_created_at": "2026-11-01T09:00:00+00:00"}])
    assert [t["tipo"] for t in bd.tarefas] == ["lead_ego_aviso"] and bd.tarefas[0]["estado"] == "concluida"
    assert len(avisos) == 1
    assunto, corpo, k = avisos[0]
    assert "já no eGO" in assunto and k["imovel_ref"] == "FH0001"
    assert "ARRENDAR" in corpo and "lead nova" in corpo and "sem resposta" not in corpo


def test_lead_fora_do_ego_continua_a_criar_a_tarefa_lead_ego(monkeypatch):
    bd, avisos = _corre(monkeypatch, [])
    assert [t["tipo"] for t in bd.tarefas] == ["lead_ego"]
    assert len(avisos) == 1 and "já no eGO" not in avisos[0][0]


def test_marca_de_entrada_anterior_nao_e_ja_no_ego(monkeypatch):
    """21/11: a marca era da 1.ª entrada (outro imóvel) e a promoção dizia «já no eGO» sobre a lead errada."""
    bd, avisos = _corre(monkeypatch, [{"id": "c1", "ego_lead_em": "2026-10-26T10:00:00+00:00", "meta_created_at": "2026-11-21T09:00:00+00:00"}])
    assert [t["tipo"] for t in bd.tarefas] == ["lead_ego"]
    assert len(avisos) == 1 and "já no eGO" not in avisos[0][0]


def test_email_e_tarefa_da_lead_qualificada_levam_o_que_a_pessoa_disse(monkeypatch):
    """Pedido #20 (25/11): o resumo da conversa chega à consultora no email e na tarefa `lead_ego`."""
    avisos = []
    monkeypatch.setattr(guards, "notificar", lambda assunto, corpo, **k: avisos.append((assunto, corpo, k)))
    monkeypatch.setattr(guards, "marcar_interesse_real", lambda *a: False)
    bd = _BD([])
    guards._promover_lead(bd, {**CLIENTE, "notas": "Quer visitar na quinta às 18h."})
    assert "O que a pessoa disse:\nQuer visitar na quinta às 18h." in avisos[0][1]
    assert "O que a pessoa disse: Quer visitar na quinta às 18h." in bd.tarefas[0]["descricao"]


def test_sem_notas_o_email_e_a_tarefa_ficam_como_antes(monkeypatch):
    bd, avisos = _corre(monkeypatch, [])
    assert "O que a pessoa disse" not in avisos[0][1] and "O que a pessoa disse" not in bd.tarefas[0]["descricao"]


def test_resumo_longo_corta_a_600_no_fim_de_frase():
    longo = "Frase um. " * 100
    r = guards._resumo_para_aviso(longo)
    assert len(r) <= 600 + 4 and r.endswith("[…]") and r.startswith("Frase um.")
    assert guards._resumo_para_aviso("  curto ") == "curto" and guards._resumo_para_aviso(None) == ""
