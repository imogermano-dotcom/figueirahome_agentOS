"""Tarefas por fazer do eGO pela API (F2.1 de `docs/fases/tarefas-pela-api-plano.md`).

Sem rede: `ego_api._pedido` é um duplo. Dados sintéticos. Os valores de data e de tipo reproduzem o que se mediu a 17/11 contra a BD.
Corre com `pytest backend/tests/`.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.integrations import ego_api, tarefas_api  # noqa: E402

TIPOS = {10: "Contactar", 11: "Follow-up/Recontactar"}
USERS = {1: "Ana Teste"}


def _t(**kw):
    base = {"objectName": "Lead", "objectId": 100, "eventTypeId": 10, "subject": "Ligar ao cliente", "dateStart": "2026-07-01T23:00:00",
            "createdDate": "2026-06-30T10:15:00", "assignedSecurityUserName": "Ana Teste", "ownerSecurityUserId": 1,
            "rescheduledDate": None, "isRescheduled": False, "eventStatusId": 4}
    return base | kw


# ── datas ─────────────────────────────────────────────────────────────────

def test_utc_no_verao_passa_ao_dia_seguinte_em_lisboa():
    assert tarefas_api.data_raw("2026-07-01T23:00:00") == "02/07/2026"
    assert tarefas_api.data_iso("2026-07-01T23:00:00") == "2026-07-02"


def test_utc_no_inverno_e_o_mesmo_dia():
    assert tarefas_api.data_raw("2026-01-10T00:00:00") == "10/01/2026"


def test_data_vazia_ou_invalida_e_none():
    assert tarefas_api.data_raw(None) is None and tarefas_api.data_raw("isto não é data") is None


# ── mapeamento ────────────────────────────────────────────────────────────

def test_mapear_da_as_colunas_do_relatorio():
    r = tarefas_api.mapear(_t(), "VEN_1", TIPOS, USERS)
    assert r == {"oportunidade_ref": "VEN_1", "tarefa_titulo": "Contactar", "tarefa_descricao": "Ligar ao cliente",
                 "tarefa_due_raw": "02/07/2026", "tarefa_due_iso": "2026-07-02", "tarefa_responsavel": "Ana Teste",
                 "tarefa_criado_por": "Ana Teste", "tarefa_status": "pendente", "tarefa_criado_em": "2026-06-30",
                 "origem_lista": "todas_as_colunas"}


def test_titulo_e_o_tipo_nao_o_subject():
    assert tarefas_api.mapear(_t(eventTypeId=11), "VEN_1", TIPOS, USERS)["tarefa_titulo"] == "Follow-up/Recontactar"


def test_reagendamento_nao_se_converte():
    """236/236 na BD com a data tal como vem; convertida, 84 ficavam um dia à frente."""
    r = tarefas_api.mapear(_t(rescheduledDate="2026-07-01T23:00:00", isRescheduled=True), "VEN_1", TIPOS, USERS)
    assert r["tarefa_reagendamento_iso"] == "2026-07-01" and r["tarefa_reagendada"] == "Sim"


def test_quem_criou_desconhecido_nao_se_escreve():
    r = tarefas_api.mapear(_t(ownerSecurityUserId=999), "VEN_1", TIPOS, USERS)
    assert "tarefa_criado_por" not in r


def test_campos_da_oportunidade_vao_para_a_tarefa():
    r = tarefas_api.mapear(_t(), "VEN_1", TIPOS, USERS, {"cliente_nome": "Cliente Teste", "tipo_oportunidade": "Venda", "url": "https://x/1"})
    assert (r["cliente_nome"], r["tipo_oportunidade"], r["url"]) == ("Cliente Teste", "Venda", "https://x/1")


def test_tipo_sem_nome_levanta():
    with pytest.raises(ego_api.EgoApiErro):
        tarefas_api.mapear(_t(eventTypeId=777), "VEN_1", TIPOS, USERS)


def test_lead_id_directa_secundaria_e_sem_lead():
    assert tarefas_api.lead_id(_t()) == 100
    assert tarefas_api.lead_id({"objectName": "VisitRoadMap", "objectId": 5, "objectSecondaryName": "Lead", "objectSecondaryId": 200}) == 200
    assert tarefas_api.lead_id({"objectName": "Entity", "objectId": 7}) is None


# ── leitura ───────────────────────────────────────────────────────────────

def test_tarefas_pendentes_pagina_e_filtra_por_estado(monkeypatch):
    pedidos = []
    paginas = {0: [_t(), _t()], 1: [_t()]}

    def _pedido(metodo, caminho, **kw):
        pedidos.append(kw["json"])
        return {"searchList": paginas[kw["json"]["pageIndex"]], "searchCount": 3}

    monkeypatch.setattr(ego_api, "_pedido", _pedido)
    assert len(ego_api.tarefas_pendentes(por_pagina=2)) == 3
    assert [p["pageIndex"] for p in pedidos] == [0, 1] and all(p["eventStatusIds"] == [1, 4] for p in pedidos)


def test_tarefas_pagina_incompleta_levanta(monkeypatch):
    monkeypatch.setattr(ego_api, "_pedido", lambda *a, **k: {"searchList": [_t()], "searchCount": 9})
    with pytest.raises(ego_api.EgoApiErro):
        ego_api.tarefas_pendentes(por_pagina=500)


def test_429_espera_e_repete(monkeypatch):
    esperas, respostas = [], [ego_api.EgoApiErro("eGO API /x: HTTP 429"), {"ok": 1}]
    monkeypatch.setattr(ego_api.time, "sleep", lambda s: esperas.append(s))

    def pedido():
        r = respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    assert ego_api._com_espera(pedido) == {"ok": 1} and esperas == [65]


def test_outro_erro_nao_se_repete(monkeypatch):
    monkeypatch.setattr(ego_api.time, "sleep", lambda s: pytest.fail("não devia esperar"))
    with pytest.raises(ego_api.EgoApiErro):
        ego_api._com_espera(lambda: (_ for _ in ()).throw(ego_api.EgoApiErro("eGO API /x: HTTP 500")))


def test_tipos_de_tarefa_usa_pt_pt(monkeypatch):
    monkeypatch.setattr(ego_api, "_pedido", lambda *a, **k: [{"id": 10, "name": {"PT-PT": "Contactar", "EN-GB": "Contact"}}, {"id": 5, "name": {"PT-PT": "X"}}])
    assert ego_api.tipos_de_tarefa() == {10: "Contactar", 5: "X"}


def test_utilizadores_junta_nome_e_apelido(monkeypatch):
    monkeypatch.setattr(ego_api, "_pedido", lambda *a, **k: [{"id": 1, "entityFirstName": "Ana", "entityLastName": " Teste "}, {"id": 2, "entityFirstName": "Rui"}])
    assert ego_api.utilizadores() == {1: "Ana Teste", 2: "Rui"}


# ── ids de lead → referência ──────────────────────────────────────────────

def _mundo_refs(monkeypatch, ativas, arquivadas, individuais):
    chamadas = {"paginas": 0, "individuais": []}
    monkeypatch.setattr(ego_api, "oportunidades_ativas", lambda: ativas)

    def _pedido(metodo, caminho, **kw):
        if caminho.endswith("GetOpportunity"):
            chamadas["individuais"].append(kw["params"]["opportunityId"])
            return {"name": individuais.get(kw["params"]["opportunityId"])}
        chamadas["paginas"] += 1
        i = kw["json"]["pageIndex"]
        return {"opportunities": arquivadas[i]}

    monkeypatch.setattr(ego_api, "_pedido", _pedido)
    return chamadas


def test_refs_so_das_ativas_nao_le_as_arquivadas(monkeypatch):
    c = _mundo_refs(monkeypatch, [{"id": 1, "name": "VEN_1"}, {"id": 2, "name": "VEN_2"}], {}, {})
    assert ego_api.refs_de_leads({1}) == {1: "VEN_1"} and c["paginas"] == 0


def test_refs_le_as_arquivadas_por_paginas_e_para_quando_completa(monkeypatch):
    pag = {0: [{"id": i, "name": f"CAP_{i}"} for i in range(500)], 1: [{"id": 900, "name": "CAP_900"}]}
    c = _mundo_refs(monkeypatch, [{"id": 1, "name": "VEN_1"}], pag, {})
    assert ego_api.refs_de_leads({1, 7, 900}) == {1: "VEN_1", 7: "CAP_7", 900: "CAP_900"} and c["paginas"] == 2


def test_refs_o_que_falta_resolve_por_get_opportunity(monkeypatch):
    c = _mundo_refs(monkeypatch, [], {0: []}, {55: "VEN_55"})
    assert ego_api.refs_de_leads({55}) == {55: "VEN_55"} and c["individuais"] == [55]


def test_refs_sem_resolucao_levanta(monkeypatch):
    _mundo_refs(monkeypatch, [], {0: []}, {})
    with pytest.raises(ego_api.EgoApiErro):
        ego_api.refs_de_leads({55})


def test_refs_demasiados_individuais_levanta_sem_chamar(monkeypatch):
    c = _mundo_refs(monkeypatch, [], {0: []}, {})
    with pytest.raises(ego_api.EgoApiErro):
        ego_api.refs_de_leads(set(range(100, 110)), max_individuais=5)
    assert c["individuais"] == []


# ── snapshot ──────────────────────────────────────────────────────────────

def test_snapshot_liga_lead_directa_e_de_roteiro_e_conta_as_sem_lead(monkeypatch):
    api = [_t(objectId=100), {**_t(), "objectName": "VisitRoadMap", "objectId": 5, "objectSecondaryName": "Lead", "objectSecondaryId": 200},
           {**_t(), "objectName": "Entity", "objectId": 7}]
    monkeypatch.setattr(ego_api, "tarefas_pendentes", lambda: api)
    monkeypatch.setattr(ego_api, "tipos_de_tarefa", lambda: TIPOS)
    monkeypatch.setattr(ego_api, "utilizadores", lambda: USERS)
    monkeypatch.setattr(ego_api, "refs_de_leads", lambda ids: {100: "VEN_1", 200: "CAP_2"} if ids == {100, 200} else pytest.fail(ids))
    s = tarefas_api.snapshot()
    assert s["brutas"] == 3 and s["sem_lead"] == 1
    assert [t["oportunidade_ref"] for t in s["tarefas"]] == ["VEN_1", "CAP_2"]
