"""Aviso de fluxo n8n falhado (`notificacoes.falha_de_workflow`). Sem rede: Supabase e email são duplos."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import notificacoes as n  # noqa: E402


class _BD:
    def __init__(self, log=()):
        self.log, self.inseridos = list(log), []

    def table(self, nome):
        return self

    def __getattr__(self, nome):
        return lambda *a, **k: self

    def insert(self, linha):
        self.inseridos.append(linha)
        return self

    def execute(self):
        return type("R", (), {"data": self.log})()


def _usa(monkeypatch, bd):
    import app.db.supabase_client as sc

    monkeypatch.setattr(sc, "get_supabase", lambda: bd)
    enviados = []
    monkeypatch.setattr(n, "notificar", lambda assunto, corpo, **k: enviados.append((assunto, corpo)))
    monkeypatch.setattr(n, "_alertas_extra", lambda: [])
    return enviados


def test_avisa_uma_vez_por_fluxo_em_12h(monkeypatch):
    bd = _BD()
    enviados = _usa(monkeypatch, bd)
    assert n.falha_de_workflow("Vigia", "Leads por dia", "OAuthException 190", "5287")["avisou"]
    assert len(enviados) == 1 and "Vigia" in enviados[0][0] and "OAuthException 190" in enviados[0][1]
    assert "Facebook Figueira Home" in enviados[0][1]  # erro de token Meta traz a pista
    assert bd.inseridos[-1]["tipo"] == "n8n_falha" and bd.inseridos[-1]["resumo"]["workflow"] == "Vigia"
    bd.log.append({"resumo": {"workflow": "Vigia"}})  # já houve aviso do Vigia há pouco
    assert n.falha_de_workflow("Vigia", "x", "outro erro", "5290") == {"avisou": False, "repetido": True}
    assert len(enviados) == 1
    assert n.falha_de_workflow("Meta leads to supabase", "Meta Lead Info", "boom", "1")["avisou"]  # outro fluxo avisa
    assert len(enviados) == 2


def test_dry_nao_envia_nem_regista(monkeypatch):
    bd = _BD()
    enviados = _usa(monkeypatch, bd)
    assert n.falha_de_workflow("Vigia", "", "x", "", dry=True) == {"avisou": False, "dry": True}
    assert enviados == [] and bd.inseridos == []


def test_erro_vazio_e_sem_pista_da_meta(monkeypatch):
    bd = _BD()
    enviados = _usa(monkeypatch, bd)
    n.falha_de_workflow("Follow-up", "Enviar", "", "")
    assert "sem detalhe" in enviados[0][1] and "Facebook" not in enviados[0][1]
