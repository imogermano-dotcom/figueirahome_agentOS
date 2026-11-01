import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from ego_api_reconciliar import comparar


def test_comparar_em_falta_estado_e_fora_da_lista():
    api = [
        {"name": "VEN_1", "leadStage": 1, "createDate": "2026-10-27T10:00:00"},  # em falta
        {"name": "VEN_2", "leadStage": 1, "createDate": "2026-10-20T10:00:00"},  # igual
        {"name": "VEN_3", "leadStage": 1, "createDate": "2026-10-01T10:00:00"},  # DB diz Perdida
    ]
    db = {"VEN_2": "Ativa", "VEN_3": "Perdida", "VEN_9": "Ativa"}  # VEN_9 já não é ativa no eGO
    r = comparar(api, db)
    assert r["em_falta_no_supabase"] == 1 and r["refs_em_falta"] == ["VEN_1"]
    assert r["em_falta_por_dia_de_criacao"] == {"2026-10-27": 1}
    assert r["estado_diferente_refs"] == ["VEN_3"]
    assert r["ativas_no_supabase_fora_da_lista"] == 1


def test_linha_de_oportunidade_so_leva_o_que_a_api_da():
    from ego_api_reconciliar import linha_de_oportunidade
    o = {"id": 7, "name": "VEN_1", "leadStage": 0, "title": "X", "phone": "", "email": None,
         "createDate": "2026-10-21T10:00:00", "alterDate": "2026-10-27T09:00:00",
         "masterLeadType": {"id": 2, "name": {"PT-PT": "Venda"}}, "leadOrigin": {"nameMls": {"PT-PT": "Outros"}},
         "assignToSecurityUserNames": ["A", "B"]}
    l = linha_de_oportunidade(o)
    assert l["oportunidade_estado"] == "Ativa" and l["tipo_oportunidade"] == "Venda" and l["origem"] == "Outros"
    assert l["responsavel"] == "A, B" and l["data_criacao_iso"] == "2026-10-21" and l["url"].endswith("/Leads/7") and l["ego_lead_id"] == 7
    assert "cliente_telefone" not in l and "cliente_email" not in l and "contacto_id" not in l


def test_pares_do_historico_so_liga_vazios_e_escolhe_a_pessoa_pelo_tipo():
    from scripts.ego_api_reconciliar import pares_do_historico
    api = [
        {"id": 1, "name": "VEN_1", "potencialClientId": 10, "ownerId": 20},
        {"id": 2, "name": "CAP_2", "potencialClientId": 10, "ownerId": 20},
        {"id": 3, "name": "VEN_3", "potencialClientId": 10},   # já tem contacto_id
        {"id": 4, "name": "VEN_4", "potencialClientId": 99},   # pessoa desconhecida
        {"id": 5, "name": "VEN_5"},                            # sem pessoa
    ]
    bd = {i: {"contacto_id": "x" if i == 3 else None} for i in range(1, 6)}
    r = pares_do_historico(api, bd, {10: "cV", 20: "cC"})
    assert [(p["oportunidade_ref"], p["contacto_id"]) for p in r] == [("VEN_1", "cV"), ("CAP_2", "cC")]
