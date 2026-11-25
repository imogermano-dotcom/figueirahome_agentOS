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


_SITE = [{"portalId": 1, "websiteId": 8662, "applicationId": 1}]


def test_plano_imovel_que_a_web_api_ve_so_muda_o_estado_quando_difere():
    api = {"W": _item("W", estado=8, portals=_SITE), "S": _item("S", estado=2, portals=_SITE)}
    p = sync.planear_imoveis_todos(api, _bd(W={"disponivel_na_api": True, "disponibilidade": "Disponível"},
                                            S={"disponivel_na_api": True, "disponibilidade": "Disponível"}))
    assert p["divergencias_web_api"] == [{"imovel_ref": "W", "no_supabase": "Disponível", "no_ego": "Retirado"}]
    (ref, valores), = p["atualizar"]
    assert ref == "W" and valores["disponibilidade"] == "Retirado" and "disponivel_na_api" not in valores


def test_plano_disponivel_fora_do_site_fica_disponivel_e_nao_publicado():
    """FH2574: Disponível no eGO, `portals` vazio, `disponivel_na_api` velho a True → estado certo e «no site» a False."""
    api = {"F": _item("F", estado=2), "V": _item("V", estado=2, portals=_SITE)}
    p = sync.planear_imoveis_todos(api, _bd(F={"disponivel_na_api": True, "disponibilidade": "Por validar"},
                                            V={"disponivel_na_api": True, "disponibilidade": "Disponível"}))
    (ref, valores), = p["atualizar"]
    assert ref == "F" and valores["disponibilidade"] == "Disponível" and valores["disponivel_na_api"] is False


def test_plano_sem_nenhum_site_na_resposta_nao_mexe_no_disponivel_na_api():
    p = sync.planear_imoveis_todos({"F": _item("F", estado=2)}, _bd(F={"disponivel_na_api": True, "disponibilidade": "Disponível"}))
    assert p["atualizar"] == []


def test_plano_manual_e_tratado_como_os_outros_e_a_flag_herdada_corrige_se():
    """Carga antiga (`manual`) sem edição à mão: estado do eGO e `disponivel_na_api` verdadeiro (fora do site = False)."""
    api = {"M": _item("M", estado=2), "S": _item("S", portals=[{"websiteId": sync._SITE_WEBSITE_ID}])}  # S: prova que o «site» do eGO é fiável
    p = sync.planear_imoveis_todos(api, _bd(M={"fonte": "manual", "disponibilidade": "Retirado", "disponivel_na_api": True}, S={}))
    v = dict(p["atualizar"])["M"]
    assert v["disponibilidade"] == "Disponível" and v["disponivel_na_api"] is False


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
    assert ("eq", "imovel_ref", "E") in filtros and ("eq", "disponivel_na_api", False) in filtros
    assert bd.logs[0]["tipo"] == "egorealestate_imoveis_todos" and bd.logs[0]["origem"] == "cron"
    assert len(bd.logs) == 1 and "morada_gps" in bd.logs[0]["resumo"]  # fase 1b dentro do mesmo log, sem 2.º registo


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


# ── angariador pelo `brokerId` (pedido #45) ───────────────────────────────

def _com_nome(**linhas):
    return _bd(**{r: {"angariador": n} for r, n in linhas.items()})


def test_nome_do_angariador_vem_do_broker_id_mais_frequente():
    api = {"A": _item("A", brokerId=7), "B": _item("B", brokerId=7), "C": _item("C", brokerId=7), "D": _item("D", brokerId=8)}
    bd = _com_nome(A="Ana Teste", B="Ana Teste", C="Outra Pessoa", D="")
    assert sync.nomes_por_broker(api, bd) == {7: "Ana Teste"}


def test_imovel_novo_leva_o_angariador_e_sem_nome_conhecido_fica_none():
    nomes = {7: "Ana Teste"}
    assert sync.mapear_imovel_novo(_item(brokerId=7), nomes)["angariador"] == "Ana Teste"
    assert sync.mapear_imovel_novo(_item(brokerId=9), nomes)["angariador"] is None
    assert sync.mapear_imovel_novo(_item(), None)["angariador"] is None


def test_plano_preenche_angariador_vazio_e_troca_o_que_o_eGO_mudou():
    api = {r: _item(r, estado=7, brokerId=7, lastUpdate="2026-10-14T14:37:10") for r in ("REF", "VAZIO", "TEM")}
    bd = _bd(REF={"angariador": "Ana Teste"}, VAZIO={"angariador": ""}, TEM={"angariador": "Outra Pessoa"})
    p = sync.planear_imoveis_todos(api, bd)
    assert {r: v["angariador"] for r, v in p["atualizar"]} == {"VAZIO": "Ana Teste", "TEM": "Ana Teste"}


def test_plano_nao_escreve_angariador_em_imovel_da_web_api():
    api = {r: _item(r, estado=7, brokerId=7, lastUpdate="2026-10-14T14:37:10") for r in ("W", "R1", "R2")}
    bd = _bd(W={"disponivel_na_api": True, "angariador": "Outra Pessoa"}, R1={"angariador": "Ana Teste"}, R2={"angariador": "Ana Teste"})
    assert sync.planear_imoveis_todos(api, bd)["atualizar"] == []


def test_manual_com_flag_herdada_a_true_recebe_o_angariador_do_eGO():
    api = {r: _item(r, brokerId=7) for r in ("M", "R1", "R2")} | {"S": _item("S", portals=[{"websiteId": sync._SITE_WEBSITE_ID}])}
    bd = _bd(M={"fonte": "manual", "disponivel_na_api": True, "angariador": "Outra Pessoa"}, R1={"angariador": "Ana Teste"}, R2={"angariador": "Ana Teste"}, S={})
    v = dict(sync.planear_imoveis_todos(api, bd)["atualizar"])["M"]
    assert v["angariador"] == "Ana Teste" and v["disponivel_na_api"] is False


def test_escritas_limitadas_por_volta_e_primeiro_o_que_muda_angariador_ou_estado(monkeypatch):
    monkeypatch.setattr(sync, "_MAX_ESCRITAS", 1)
    api = [_item("F", id=1, estado=7), _item("A", id=2, estado=7, brokerId=7), _item("R1", id=3, estado=7, brokerId=7),
           _item("R2", id=4, estado=7, brokerId=7), _item("S", id=5, estado=7, portals=[{"websiteId": sync._SITE_WEBSITE_ID}])]
    linhas = list(_bd(R1={"angariador": "Ana Teste"}, R2={"angariador": "Ana Teste"}, F={"fonte": "manual", "disponivel_na_api": True},
                      A={"angariador": "Outra Pessoa"}, S={"disponivel_na_api": True}).values())
    bd = _mundo(monkeypatch, api, linhas)
    r = asyncio.run(sync.sync_imoveis_todos("cron", dry=False))
    assert (r["atualizados"], r["adiados"]) == (1, 1) and bd.updates[0][1][0] == ("eq", "imovel_ref", "A")
