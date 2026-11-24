from app.api import oportunidades_sync as sync
from app.config import settings
from app.integrations import ego_notas


def _n(ref, dia, ego_id):
    return {"ref": ref, "dia": dia, "ego_id": ego_id}


def test_so_a_mais_antiga_de_cada_oportunidade_e_conta_as_adiadas():
    novas = [_n("VEN_1", "2026-11-23", 3), _n("VEN_1", "2026-11-22", 2), _n("VEN_1", "2026-11-22", 1), _n("VEN_2", "2026-11-23", 4)]
    agora, adiadas = ego_notas.uma_por_oportunidade(novas)
    assert sorted(n["ego_id"] for n in agora) == [1, 4] and adiadas == 2


def test_reconciliar_grava_so_uma_por_oportunidade(monkeypatch):
    gravadas = []
    monkeypatch.setattr(settings, "notas_api_ego", "1")
    monkeypatch.setattr(ego_notas, "novas", lambda desde="": [_n("VEN_1", "2026-11-23", 2), _n("VEN_1", "2026-11-22", 1)])
    monkeypatch.setattr(ego_notas, "gravar", lambda n, origem="manual": gravadas.extend(n) or {"inseridas": len(n), "erros": {}})
    r = sync.reconciliar_notas()
    assert [n["ego_id"] for n in gravadas] == [1] and r["gravadas"] == 1 and r["adiadas"] == 1 and r["por_gravar"] == 2
