"""Oportunidades apagadas no eGO (`docs/fases/oportunidades-apagadas-plano.md`, pedido #31, migration 0054).

Uma apagada deixa de vir nos relatórios e ficava «Ativa» para sempre. Arquivada NÃO é apagada. Sem rede.
"""

import asyncio
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import leads_para_ego as lp  # noqa: E402
from app.api import oportunidades_sync as sync  # noqa: E402
from app.api.deps import require_sync_access  # noqa: E402
from app.integrations import ego_api  # noqa: E402

HOJE = date(2026, 10, 26)


# ── a API ─────────────────────────────────────────────────────────────────

def test_refs_ativas_devolve_os_nomes(monkeypatch):
    monkeypatch.setattr(ego_api, "_pedido", lambda *a, **k: {"opportunities": [{"name": "VEN_1"}, {"name": "VEN_2"}, {}], "totalRows": 3})
    assert ego_api.refs_ativas() == {"VEN_1", "VEN_2"}


def test_refs_ativas_com_lista_parcial_levanta(monkeypatch):
    monkeypatch.setattr(ego_api, "_pedido", lambda *a, **k: {"opportunities": [{"name": "VEN_1"}], "totalRows": 9})
    with pytest.raises(ego_api.EgoApiErro):
        ego_api.refs_ativas()


@pytest.mark.parametrize("resposta,apagada", [({"fieldStatusId": 1, "archived": False}, True), ({"fieldStatusId": 0, "archived": True}, False),
                                              ({"fieldStatusId": 0, "archived": False}, False)])
def test_so_fieldstatus_1_e_apagada_arquivada_nao(monkeypatch, resposta, apagada):
    monkeypatch.setattr(ego_api, "_pedido", lambda *a, **k: resposta)
    assert ego_api.oportunidade_apagada(1) is apagada


def test_404_conta_como_apagada_outro_erro_levanta(monkeypatch):
    def _404(*a, **k):
        raise ego_api.EgoApiErro("eGO API /x: HTTP 404")

    def _500(*a, **k):
        raise ego_api.EgoApiErro("eGO API /x: HTTP 500")

    monkeypatch.setattr(ego_api, "_pedido", _404)
    assert ego_api.oportunidade_apagada(1) is True
    monkeypatch.setattr(ego_api, "_pedido", _500)
    with pytest.raises(ego_api.EgoApiErro):
        ego_api.oportunidade_apagada(1)


def test_pedido_junta_os_params_ao_application_id_e_nao_poe_query_no_caminho(monkeypatch):
    """httpx 0.28 (Fly) troca a query do URL pelo `params=`: o id da oportunidade perdia-se e o eGO respondia 400 (26/10)."""
    visto = {}

    class _Resp:
        status_code = 200
        request = type("R", (), {"url": type("U", (), {"path": "/x"})()})()

        def json(self):
            return {"fieldStatusId": 1}

    class _Cliente:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def request(self, metodo, url, **kw):
            visto.update(url=url, **kw)
            return _Resp()

    monkeypatch.setattr(ego_api.httpx, "Client", _Cliente)
    monkeypatch.setattr(ego_api, "_sessao_valida", lambda c: {"application_id": 6429, "token": "t"})
    monkeypatch.setattr(ego_api, "_dados", lambda r: r.json())
    assert ego_api.oportunidade_apagada(60617326) is True
    assert "?" not in visto["url"] and visto["params"] == {"applicationId": 6429, "opportunityId": 60617326}


# ── a reconciliação ───────────────────────────────────────────────────────

class _BD:
    def __init__(self, linhas):
        self.linhas, self.updates, self._upd, self._filtro = linhas, [], None, None

    def table(self, nome):
        assert nome == "oportunidades"
        return self

    def select(self, *a):
        self._upd = None
        return self

    def gte(self, *a):
        return self

    def order(self, *a):
        return self

    def range(self, i, f):
        self._i, self._f = i, f
        return self

    def update(self, valores):
        self._upd = valores
        return self

    def eq(self, _, valor):
        if self._upd is not None:
            self.updates.append((valor, self._upd))
        return self

    def execute(self):
        if self._upd is not None:
            return type("R", (), {"data": []})()
        return type("R", (), {"data": self.linhas[self._i:self._f + 1]})()


def _linha(ref, apagada=False, url=None):
    return {"oportunidade_ref": ref, "url": url if url is not None else f"https://admin.egorealestate.com/egocore/Leads/{ref[-3:]}",
            "apagada_no_ego": apagada}


def _mundo(monkeypatch, linhas, ativas, apagadas=()):
    bd = _BD(linhas)
    confirmadas = []

    def _confirmar(i):
        confirmadas.append(str(i))
        return str(i) in apagadas

    monkeypatch.setattr(sync, "get_supabase", lambda: bd)
    monkeypatch.setattr(ego_api, "refs_ativas", lambda: set(ativas))
    monkeypatch.setattr(ego_api, "oportunidade_apagada", _confirmar)
    return bd, confirmadas


def test_candidata_apagada_e_marcada(monkeypatch):
    bd, _ = _mundo(monkeypatch, [_linha("VEN_111"), _linha("VEN_222")], ativas={"VEN_222"}, apagadas={"111"})
    r = sync.reconciliar_apagadas(HOJE)
    assert r["marcadas"] == ["VEN_111"] and r["erros"] == 0
    (ref, valores), = bd.updates
    assert ref == "VEN_111" and valores["apagada_no_ego"] is True and valores["apagada_em"]


def test_arquivada_nao_e_marcada(monkeypatch):
    """Falta na lista ativa mas o eGO diz que não está apagada (só arquivada): não se marca."""
    bd, confirmadas = _mundo(monkeypatch, [_linha("VEN_333")], ativas=set(), apagadas=set())
    r = sync.reconciliar_apagadas(HOJE)
    assert r["marcadas"] == [] and confirmadas == ["333"] and bd.updates == []


def test_so_confirma_as_que_faltam_na_lista_ativa_e_ainda_nao_marcadas(monkeypatch):
    bd, confirmadas = _mundo(monkeypatch, [_linha("VEN_111"), _linha("VEN_222"), _linha("VEN_333", apagada=True), _linha("VEN_444", url="")],
                             ativas={"VEN_111"}, apagadas=set())
    sync.reconciliar_apagadas(HOJE)
    assert confirmadas == ["222"], "ativa, já marcada e sem url não se confirmam"


def test_marcada_que_volta_a_lista_ativa_e_desmarcada(monkeypatch):
    bd, _ = _mundo(monkeypatch, [_linha("VEN_555", apagada=True)], ativas={"VEN_555"})
    r = sync.reconciliar_apagadas(HOJE)
    assert r["desmarcadas"] == ["VEN_555"] and bd.updates == [("VEN_555", {"apagada_no_ego": False, "apagada_em": None})]


def test_limite_por_volta_e_adiadas(monkeypatch):
    monkeypatch.setattr(sync, "_LIMITE_APAGADAS", 2)
    linhas = [_linha(f"VEN_{i:03d}") for i in range(5)]
    _, confirmadas = _mundo(monkeypatch, linhas, ativas=set(), apagadas=set())
    r = sync.reconciliar_apagadas(HOJE)
    assert len(confirmadas) == 2 and r["adiadas"] == 3 and r["candidatas"] == 5


def test_erro_a_confirmar_conta_e_nao_marca(monkeypatch):
    bd, _ = _mundo(monkeypatch, [_linha("VEN_111")], ativas=set())

    def _rebenta(i):
        raise ego_api.EgoApiErro("eGO API: HTTP 500")

    monkeypatch.setattr(ego_api, "oportunidade_apagada", _rebenta)
    r = sync.reconciliar_apagadas(HOJE)
    assert r["erros"] == 1 and r["marcadas"] == [] and bd.updates == []


def test_pagina_ordenada_nao_perde_linhas(monkeypatch):
    linhas = [_linha(f"VEN_{i:04d}") for i in range(1500)]
    _, confirmadas = _mundo(monkeypatch, linhas, ativas=set(), apagadas=set())
    monkeypatch.setattr(sync, "_LIMITE_APAGADAS", 5000)
    sync.reconciliar_apagadas(HOJE)
    assert len(confirmadas) == 1500, "as duas páginas de 1000 e 500"


# ── o endpoint ────────────────────────────────────────────────────────────

def _cliente(monkeypatch, propostas=None, apagadas=None, falha_propostas=None, falha_apagadas=None):
    avisos, registos = [], []

    def _p():
        if falha_propostas:
            raise falha_propostas
        return dict(propostas or {"na_api": 1})

    def _a():
        if falha_apagadas:
            raise falha_apagadas
        return apagadas or {"marcadas": []}

    async def _aviso(*a, **k):
        avisos.append(a)

    async def _log(resumo, origem, tipo="x"):
        registos.append((resumo, tipo))

    monkeypatch.setattr(sync, "reconciliar_propostas", _p)
    monkeypatch.setattr(sync, "reconciliar_apagadas", _a)
    monkeypatch.setattr(sync, "falha_de_sync", _aviso)
    monkeypatch.setattr(sync, "_log_execucao", _log)
    app = FastAPI()
    app.include_router(sync.router)
    app.dependency_overrides[require_sync_access] = lambda: "sync-secret"
    return TestClient(app), avisos, registos


def test_endpoint_corre_as_duas_partes(monkeypatch):
    c, avisos, registos = _cliente(monkeypatch, apagadas={"marcadas": ["VEN_1"]})
    r = c.post("/api/oportunidades/sync/propostas")
    assert r.status_code == 200 and r.json() == {"na_api": 1, "apagadas": {"marcadas": ["VEN_1"]}} and avisos == [] and len(registos) == 1


def test_falha_das_apagadas_nao_esconde_as_propostas(monkeypatch):
    c, avisos, registos = _cliente(monkeypatch, falha_apagadas=RuntimeError("503"))
    r = c.post("/api/oportunidades/sync/propostas")
    assert r.status_code == 200 and r.json()["na_api"] == 1 and "apagadas" in r.json()["falhas"][0] and len(avisos) == 1


def test_falha_das_propostas_nao_esconde_as_apagadas(monkeypatch):
    c, avisos, _ = _cliente(monkeypatch, falha_propostas=RuntimeError("503"), apagadas={"marcadas": ["VEN_1"]})
    r = c.post("/api/oportunidades/sync/propostas")
    assert r.status_code == 200 and r.json()["apagadas"] == {"marcadas": ["VEN_1"]} and len(avisos) == 1


def test_falha_das_duas_devolve_502(monkeypatch):
    c, avisos, _ = _cliente(monkeypatch, falha_propostas=RuntimeError("a"), falha_apagadas=RuntimeError("b"))
    assert c.post("/api/oportunidades/sync/propostas").status_code == 502 and len(avisos) == 1


# ── o consumidor ──────────────────────────────────────────────────────────

def test_oportunidade_apagada_ja_nao_bloqueia_a_lead(monkeypatch):
    filtros = []

    class _Q:
        def __getattr__(self, nome):
            if nome == "not_":
                return self
            return lambda *a, **k: self

        def eq(self, campo, valor):
            filtros.append((campo, valor))
            return self

        def ilike(self, *a):
            return self

        def execute(self):
            return type("R", (), {"data": []})()

    monkeypatch.setattr(lp, "get_supabase", lambda: type("S", (), {"table": lambda self, n: _Q()})())
    lp._responsavel_da_oportunidade("912345678", "x@example.com")
    assert ("apagada_no_ego", False) in filtros and ("oportunidade_estado", "Ativa") in filtros


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
