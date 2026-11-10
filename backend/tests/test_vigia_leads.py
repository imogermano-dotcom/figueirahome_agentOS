"""Vigia das leads da Meta (`docs/fases/vigia-leads-meta-plano.md`). Sem rede: Supabase e email são duplos."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import vigia_leads as v  # noqa: E402


def test_so_conta_quando_a_meta_tem_mais():
    assert v.diferencas({"2026-11-02": 15, "2026-11-03": 11}, {"2026-11-02": 15, "2026-11-03": 9}) == {"2026-11-03": 2}
    assert v.diferencas({"2026-11-02": 10}, {"2026-11-02": 12}) == {}  # Supabase a mais (recrutamento, formulários): ok


def test_falta_confirmada_so_se_repete_na_verificacao_anterior():
    assert v.confirmadas({"d1": 2}, {}) == {}
    assert v.confirmadas({"d1": 2}, {"d1": 1}) == {"d1": 1}  # vale o menor
    assert v.confirmadas({"d1": 1}, {"d2": 3}) == {}


class _BD:
    """Duplo de `contactos` + `agente_sync_log`."""

    def __init__(self, meta_created_at, log=()):
        self.contactos, self.log, self.inseridos, self._t, self._tipo = [{"meta_created_at": m} for m in meta_created_at], list(log), [], None, None

    def table(self, nome):
        self._t, self._tipo = nome, None
        return self

    def __getattr__(self, nome):
        if nome == "not_":
            return self
        return lambda *a, **k: self

    def eq(self, coluna, valor):
        if coluna == "tipo":
            self._tipo = valor
        return self

    def insert(self, linha):
        self.inseridos.append(linha)
        return self

    def execute(self):
        if self._t == "contactos":
            return type("R", (), {"data": self.contactos})()
        return type("R", (), {"data": [l for l in self.log if l["tipo"] == self._tipo][:1] if self._tipo else []})()


def _usa(monkeypatch, bd):
    monkeypatch.setattr(v, "get_supabase", lambda: bd)
    enviados = []
    monkeypatch.setattr(v, "notificar", lambda assunto, corpo, **k: enviados.append((assunto, corpo)))
    monkeypatch.setattr(v, "_alertas_extra", lambda: [])
    return enviados


NOITE = "2026-11-03T22:30:00+00:00"  # 22:30 em Lisboa (inverno)


def test_dias_em_hora_de_lisboa(monkeypatch):
    bd = _BD(["2026-11-02T23:30:00+00:00", "2026-11-03T08:00:00+00:00"])  # 23:30 UTC de 02/11 ainda é 02/11 em Lisboa (UTC+0)
    _usa(monkeypatch, bd)
    assert v.contar_no_supabase(["2026-11-02", "2026-11-03"]) == {"2026-11-02": 1, "2026-11-03": 1}


def test_primeira_vez_regista_mas_nao_avisa(monkeypatch):
    bd = _BD([NOITE])
    enviados = _usa(monkeypatch, bd)
    r = v.verificar({"2026-11-03": 3})
    assert r["diferencas"] == {"2026-11-03": 2} and r["confirmadas"] == {} and not r["avisou"] and enviados == []
    assert bd.inseridos[0]["tipo"] == v.TIPO_VERIFICACAO


def test_segunda_vez_avisa_uma_vez(monkeypatch):
    log = [{"tipo": v.TIPO_VERIFICACAO, "resumo": {"diferencas": {"2026-11-03": 2}}}]
    bd = _BD([NOITE], log)
    enviados = _usa(monkeypatch, bd)
    r = v.verificar({"2026-11-03": 3})
    assert r["avisou"] and r["confirmadas"] == {"2026-11-03": 2}
    assert len(enviados) == 1 and "2" in enviados[0][0] and "Meta 3" in enviados[0][1] and "Supabase 1" in enviados[0][1]
    assert bd.inseridos[-1]["tipo"] == v.TIPO_ALERTA


def test_mesmo_aviso_nao_se_repete(monkeypatch):
    log = [{"tipo": v.TIPO_VERIFICACAO, "resumo": {"diferencas": {"2026-11-03": 2}}},
           {"tipo": v.TIPO_ALERTA, "resumo": {"faltam": {"2026-11-03": 2}}}]
    bd = _BD([NOITE], log)
    enviados = _usa(monkeypatch, bd)
    r = v.verificar({"2026-11-03": 3})
    assert r.get("repetido") and not r["avisou"] and enviados == []


def test_dry_nao_regista_nem_avisa(monkeypatch):
    log = [{"tipo": v.TIPO_VERIFICACAO, "resumo": {"diferencas": {"2026-11-03": 2}}}]
    bd = _BD([NOITE], log)
    enviados = _usa(monkeypatch, bd)
    r = v.verificar({"2026-11-03": 3}, dry=True)
    assert r["confirmadas"] == {"2026-11-03": 2} and enviados == [] and bd.inseridos == []


def test_tudo_certo_nao_avisa(monkeypatch):
    bd = _BD([NOITE])
    enviados = _usa(monkeypatch, bd)
    assert v.verificar({"2026-11-03": 1})["diferencas"] == {} and enviados == []


def test_endpoint_rejeita_corpo_invalido():
    from pydantic import ValidationError

    from app.api.leads_vigia import LeadsDaMeta

    LeadsDaMeta(dias={"2026-11-03": 3})
    for mau in ({}, {"hoje": 3}, {"2026-11-03": -1}, {f"2026-11-0{i}": 1 for i in range(1, 9)}):
        with pytest.raises(ValidationError):
            LeadsDaMeta(dias=mau)


def test_falha_do_vigia_avisa_uma_vez_em_12h(monkeypatch):
    bd = _BD([])
    enviados = _usa(monkeypatch, bd)
    assert v.avisar_falha("OAuthException 190")["avisou"] and len(enviados) == 1
    assert "OAuthException 190" in enviados[0][1] and "Facebook Figueira Home" in enviados[0][1]
    assert bd.inseridos[-1]["tipo"] == v.TIPO_FALHA
    bd.log.append({"tipo": v.TIPO_FALHA, "resumo": {}})  # já houve aviso há pouco
    r = v.avisar_falha("OAuthException 190")
    assert r == {"avisou": False, "repetido": True} and len(enviados) == 1


def test_falha_do_vigia_dry_nao_envia(monkeypatch):
    bd = _BD([])
    enviados = _usa(monkeypatch, bd)
    assert v.avisar_falha("x", dry=True) == {"avisou": False, "dry": True} and enviados == [] and bd.inseridos == []
