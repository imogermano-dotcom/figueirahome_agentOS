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
        self.filtros = []

    def table(self, nome):
        self._t, self._tipo = nome, None
        return self

    def __getattr__(self, nome):
        if nome == "not_":
            return self
        return lambda *a, **k: (self.filtros.append((nome, a)), self)[1]

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


def test_so_conta_leads_de_anuncio(monkeypatch):
    bd = _BD([NOITE])
    _usa(monkeypatch, bd)
    v.contar_no_supabase(["2026-11-03"])
    assert ("is_", ("ad_id", "null")) in bd.filtros  # testes e leads orgânicas (sem ad_id) não tapam a falta de uma real


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


def test_ids_em_falta_so_os_que_nao_estao_no_supabase(monkeypatch):
    monkeypatch.setattr(v, "_existentes", lambda ids: {"1111111111"} & ids)
    r = v.ids_em_falta({"d1": ["1111111111", "2222222222"], "d2": ["3333333333"]}, ["d1"])
    assert r == {"d1": ["2222222222"]}  # d2 não foi pedido; o id já gravado não conta


def test_alerta_lista_ids_e_avisa_se_a_lista_vem_incompleta():
    t = v.texto_do_alerta({"d1": 2}, {"d1": 3}, {"d1": 1}, {"d1": ["2222222222"]}, {"d1": ["1111111111", "2222222222"]})
    assert "2222222222" in t and "incompleta (2 de 3)" in t and "Make" in t
    sem = v.texto_do_alerta({"d1": 2}, {"d1": 3}, {"d1": 1})
    assert "ids da Meta" not in sem and "contagens, não ids" in sem


def test_verificar_com_ids_manda_os_ids_no_email(monkeypatch):
    log = [{"tipo": v.TIPO_VERIFICACAO, "resumo": {"diferencas": {"2026-11-03": 2}}}]
    bd = _BD([NOITE], log)
    enviados = _usa(monkeypatch, bd)
    monkeypatch.setattr(v, "_existentes", lambda ids: set())
    r = v.verificar({"2026-11-03": 3}, ids={"2026-11-03": ["4444444444", "5555555555", "6666666666"]})
    assert r["ids_em_falta"] == {"2026-11-03": ["4444444444", "5555555555", "6666666666"]} and "4444444444" in enviados[0][1]


def test_falha_a_comparar_ids_nao_impede_o_aviso(monkeypatch):
    log = [{"tipo": v.TIPO_VERIFICACAO, "resumo": {"diferencas": {"2026-11-03": 2}}}]
    bd = _BD([NOITE], log)
    enviados = _usa(monkeypatch, bd)
    monkeypatch.setattr(v, "_existentes", lambda ids: (_ for _ in ()).throw(RuntimeError("bd em baixo")))
    r = v.verificar({"2026-11-03": 3}, ids={"2026-11-03": ["4444444444"]})
    assert r["avisou"] and len(enviados) == 1


def test_endpoint_valida_os_ids():
    from pydantic import ValidationError

    from app.api.leads_vigia import LeadsDaMeta

    LeadsDaMeta(dias={"2026-11-03": 1}, ids={"2026-11-03": ["1234567890123456"]})
    LeadsDaMeta(dias={"2026-11-03": 1})  # sem ids: o corpo antigo continua a valer
    for mau in ({"2026-11-03": ["abc"]}, {"2026-11-03": ["12"]}, {"hoje": ["1234567890"]}):
        with pytest.raises(ValidationError):
            LeadsDaMeta(dias={"2026-11-03": 1}, ids=mau)
