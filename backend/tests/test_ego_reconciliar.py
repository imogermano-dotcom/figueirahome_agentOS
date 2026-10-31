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
