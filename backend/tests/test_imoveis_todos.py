"""Imóveis de todos os estados pela API nova do eGO (`docs/fases/imoveis-todos-os-estados-plano.md`, pedido #45).

A Web API pública só lista os publicados; este sync traz o resto sem nunca publicar nada nem apagar linhas.
Sem rede: a API do eGO e o Supabase são duplos. Corre com `pytest backend/tests/`.
"""

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import imoveis_sync as api_sync  # noqa: E402
from app.api.deps import require_sync_access  # noqa: E402
from app.integrations import ego_api, imoveis_sync as sync  # noqa: E402


def _item(ref="FH1", estado=7, **kw):
    base = {"reference": ref, "id": 1, "realestateStatusId": estado, "fieldStatusId": 0, "lastUpdate": "2026-10-14T14:37:10",
            "createDate": "2026-10-01T10:00:00", "name": {"PT-PT": "T2 em Teste"}, "rooms": 2, "bathrooms": 1, "nettArea": 78.0,
            "grossArea": 90.0, "landArea": None, "businesses": []}
    return base | kw


def _venda(valor):
    return [{"businessTypeId": 1, "prices": [{"value": valor}]}]


# ── API ───────────────────────────────────────────────────────────────────

def test_todos_os_imoveis_pagina_ate_acabar(monkeypatch):
    paginas = {0: [{"reference": f"A{i}"} for i in range(3)], 1: [{"reference": "B0"}]}
    pedidos = []

    def _pedido(metodo, caminho, **kw):
        pedidos.append(kw["json"]["pageIndex"])
        return {"realestates": paginas[kw["json"]["pageIndex"]], "totalRows": 4}

    monkeypatch.setattr(ego_api, "_pedido", _pedido)
    assert len(ego_api.todos_os_imoveis(por_pagina=3)) == 4 and pedidos == [0, 1]


def test_pagina_incompleta_levanta(monkeypatch):
    monkeypatch.setattr(ego_api, "_pedido", lambda *a, **k: {"realestates": [{"reference": "A"}], "totalRows": 9})
    with pytest.raises(ego_api.EgoApiErro):
        ego_api.todos_os_imoveis(por_pagina=500)


def test_uma_linha_por_referencia_fica_a_ativa_mais_recente():
    lista = [_item("X", id=1, lastUpdate="2026-01-01T00:00:00"), _item("X", id=2, lastUpdate="2026-09-01T00:00:00"),
             _item("X", id=3, lastUpdate="2026-12-01T00:00:00", fieldStatusId=1), _item("Y", id=5), {"reference": "  "}, {}]
    r = ego_api.um_por_referencia(lista)
    assert set(r) == {"X", "Y"} and r["X"]["id"] == 2, "a apagada (fieldStatusId 1) perde, mesmo sendo a mais recente"


# ── mapeamento ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("codigo,texto", [(2, "Disponível"), (3, "Vendido"), (4, "Reservado"), (5, "Arrendado"),
                                           (7, "Em Prospecção"), (8, "Retirado"), (9, "Por validar")])
def test_estado_do_ego_para_disponibilidade(codigo, texto):
    assert sync.mapear_imovel_novo(_item(estado=codigo))["disponibilidade"] == texto


def test_imovel_novo_nunca_entra_publicado_nem_com_preco():
    """`publicado` é GENERATED (Disponível + preço + disponivel_na_api): o imóvel novo tem de entrar com a coluna a False."""
    r = sync.mapear_imovel_novo(_item(estado=2, businesses=_venda(100000)))
    assert r["disponivel_na_api"] is False and r["fonte"] == "egorealestate" and r["venda_preco"] == 100000.0


def test_campos_e_precos():
    r = sync.mapear_imovel_novo(_item(businesses=_venda(250000) + [{"businessTypeId": 2, "prices": [{"value": 900}]}]))
    assert (r["titulo"], r["quartos"], r["casas_banho"], r["area_util"], r["area_bruta"]) == ("T2 em Teste", 2, 1, 78.0, 90.0)
    assert (r["venda_preco"], r["arrendamento_preco"], r["data_criacao"], r["data_alteracao"]) == (250000.0, 900.0, "2026-10-01", "2026-10-14")
    assert r["ego_atualizado_em"] == "2026-10-14T13:37:10+00:00", "hora de Lisboa (verão, UTC+1) passada a UTC"


def test_sem_valor_vira_none():
    r = sync.mapear_imovel_novo(_item(rooms=-2147483648, bathrooms=None, name=None, nettArea=0))
    assert r["quartos"] is None and r["casas_banho"] is None and r["titulo"] is None and r["area_util"] is None


def test_todas_as_linhas_novas_tem_as_mesmas_chaves():
    """Chaves diferentes num upsert por lotes escrevem NULL nas outras linhas (custou 40 coordenadas a 12/08)."""
    a = sync.mapear_imovel_novo(_item(businesses=_venda(1)))
    b = sync.mapear_imovel_novo({"reference": "Z", "realestateStatusId": 9})
    assert set(a) == set(b)


# ── o plano ───────────────────────────────────────────────────────────────

def _bd(**linhas):
    return {r: {"imovel_ref": r, "fonte": "egorealestate", "disponibilidade": "Em Prospecção", "disponivel_na_api": False,
                "ego_atualizado_em": "2026-10-14T13:37:10+00:00"} | v for r, v in linhas.items()}


def test_plano_novo_insere():
    p = sync.planear_imoveis_todos({"N": _item("N")}, {})
    assert [x["imovel_ref"] for x in p["inserir"]] == ["N"] and p["atualizar"] == []


def test_plano_imovel_que_a_web_api_ve_nao_se_escreve():
    p = sync.planear_imoveis_todos({"W": _item("W", estado=8)}, _bd(W={"disponivel_na_api": True, "disponibilidade": "Disponível"}))
    assert p["atualizar"] == [] and p["divergencias_web_api"] == [{"imovel_ref": "W", "no_supabase": "Disponível", "no_ego": "Retirado"}]


def test_plano_manual_nunca_se_escreve():
    p = sync.planear_imoveis_todos({"M": _item("M", estado=2)}, _bd(M={"fonte": "manual", "disponibilidade": "Retirado"}))
    assert p["atualizar"] == [] and p["divergencias_manual"][0]["imovel_ref"] == "M"


def test_plano_existente_nao_visto_atualiza_estado_e_data():
    p = sync.planear_imoveis_todos({"E": _item("E", estado=3, lastUpdate="2026-10-20T10:00:00")}, _bd(E={"disponibilidade": "Por validar"}))
    assert p["atualizar"] == [("E", {"disponibilidade": "Vendido", "ego_atualizado_em": "2026-10-20T09:00:00+00:00"})]


def test_plano_so_data_mais_recente_atualiza_e_igual_nao_faz_nada():
    nova = sync.planear_imoveis_todos({"E": _item("E", estado=7, lastUpdate="2026-11-01T10:00:00")}, _bd(E={}))
    assert len(nova["atualizar"]) == 1
    igual = sync.planear_imoveis_todos({"E": _item("E", estado=7, lastUpdate="2026-10-14T14:37:10")}, _bd(E={}))
    assert igual["atualizar"] == []


def test_plano_estado_desconhecido_e_ignorado_e_contado():
    p = sync.planear_imoveis_todos({"D": _item("D", estado=99)}, {})
    assert p["desconhecidos"] == 1 and p["inserir"] == [] and p["atualizar"] == []


# ── a execução ────────────────────────────────────────────────────────────

class _Tabela:
    def __init__(self, bd):
        self.bd, self._op, self._filtros = bd, None, []

    def select(self, *a):
        self._op = "select"
        return self

    def range(self, inicio, fim):
        self._intervalo = (inicio, fim)
        return self

    def upsert(self, lote, **kw):
        self.bd.upserts.append((lote, kw))
        self._op = "upsert"
        return self

    def update(self, valores):
        self._op, self._valores, self._filtros = "update", valores, []
        return self

    def delete(self, *a, **k):
        pytest.fail("este sync nunca apaga linhas")

    def eq(self, c, v):
        self._filtros.append(("eq", c, v))
        return self

    def neq(self, c, v):
        self._filtros.append(("neq", c, v))
        return self

    def insert(self, dados):
        self.bd.logs.append(dados)
        self._op = "insert"
        return self

    def execute(self):
        if self._op == "update":
            self.bd.updates.append((self._valores, self._filtros))
        if self._op == "select":
            i, f = self._intervalo
            return type("R", (), {"data": self.bd.linhas[i:f + 1]})()
        return type("R", (), {"data": []})()


class _BD:
    def __init__(self, linhas):
        self.linhas, self.upserts, self.updates, self.logs = linhas, [], [], []

    def table(self, nome):
        return _Tabela(self)


def _mundo(monkeypatch, api, linhas):
    bd = _BD(linhas)
    monkeypatch.setattr(sync, "get_supabase", lambda: bd)
    monkeypatch.setattr(ego_api, "todos_os_imoveis", lambda: api)
    return bd


def test_dry_nao_escreve_nada(monkeypatch):
    bd = _mundo(monkeypatch, [_item("N"), _item("E", estado=3)], list(_bd(E={"disponibilidade": "Por validar"}).values()))
    r = asyncio.run(sync.sync_imoveis_todos("manual", dry=True))
    assert (r["a_inserir"], r["a_atualizar"], r["inseridos"], r["atualizados"]) == (1, 1, 0, 0)
    assert bd.upserts == [] and bd.updates == [] and bd.logs == []


def test_execucao_insere_em_lotes_com_ignore_duplicates_e_atualiza_com_condicoes(monkeypatch):
    monkeypatch.setattr(sync, "_LOTE_INSERT", 2)
    api = [_item(f"N{i}", id=i) for i in range(5)] + [_item("E", id=99, estado=3)]
    bd = _mundo(monkeypatch, api, list(_bd(E={"disponibilidade": "Por validar"}).values()))
    r = asyncio.run(sync.sync_imoveis_todos("cron", dry=False))
    assert (r["inseridos"], r["atualizados"], r["erros"]) == (5, 1, 0)
    assert [len(l) for l, _ in bd.upserts] == [2, 2, 1]
    assert all(k == {"on_conflict": "imovel_ref", "ignore_duplicates": True} for _, k in bd.upserts)
    assert all(l["disponivel_na_api"] is False for lote, _ in bd.upserts for l in lote)
    (valores, filtros), = bd.updates
    assert valores["disponibilidade"] == "Vendido"
    assert ("eq", "imovel_ref", "E") in filtros and ("eq", "disponivel_na_api", False) in filtros and ("neq", "fonte", "manual") in filtros
    assert bd.logs[0]["tipo"] == "egorealestate_imoveis_todos" and bd.logs[0]["origem"] == "cron"


def test_falha_num_lote_conta_erros_e_continua(monkeypatch):
    bd = _mundo(monkeypatch, [_item("N1"), _item("N2", id=2)], [])
    original = bd.table

    def _table(nome):
        t = original(nome)
        t.upsert = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("503"))
        return t

    monkeypatch.setattr(bd, "table", _table)
    r = asyncio.run(sync.sync_imoveis_todos("manual", dry=False))
    assert r["erros"] == 2 and r["inseridos"] == 0


# ── o endpoint ────────────────────────────────────────────────────────────

def _cliente(monkeypatch, resultado=None, falha=None):
    chamadas, avisos = [], []

    async def _sync(origem, dry):
        chamadas.append((origem, dry))
        if falha:
            raise falha
        return resultado

    async def _aviso(*a, **k):
        avisos.append(a)

    monkeypatch.setattr(api_sync, "sync_imoveis_todos", _sync)
    monkeypatch.setattr(api_sync, "falha_de_sync", _aviso)
    app = FastAPI()
    app.include_router(api_sync.router)
    app.dependency_overrides[require_sync_access] = lambda: "sync-secret"
    return TestClient(app), chamadas, avisos


def test_endpoint_passa_o_dry_e_a_origem(monkeypatch):
    c, chamadas, _ = _cliente(monkeypatch, resultado={"a_inserir": 1})
    assert c.post("/api/imoveis/sync/egorealestate/todos?dry=1").json() == {"a_inserir": 1}
    assert c.post("/api/imoveis/sync/egorealestate/todos").status_code == 200
    assert chamadas == [("cron", True), ("cron", False)]


def test_endpoint_falha_devolve_502_e_avisa(monkeypatch):
    c, _, avisos = _cliente(monkeypatch, falha=RuntimeError("503"))
    assert c.post("/api/imoveis/sync/egorealestate/todos").status_code == 502 and len(avisos) == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
