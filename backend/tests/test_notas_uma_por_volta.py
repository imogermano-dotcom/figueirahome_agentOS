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


def test_gravar_salta_a_nota_de_oportunidade_que_ainda_nao_existe(monkeypatch):
    """26/11: notas de oportunidades criadas hoje no eGO davam 23503 todas as horas; agora contam-se à parte."""
    inseridas, logs = [], []

    class _BD:
        def table(self, nome):
            self.nome = nome
            return self

        def select(self, *_):
            return self

        def in_(self, *_):
            return self

        def insert(self, linha):
            (inseridas if self.nome == "notas" else logs).append(linha)
            return self

        def rpc(self, *_):
            return self

        def execute(self):
            dados = [{"oportunidade_ref": "VEN_1", "url": "u", "cliente_nome": None}] if self.nome == "oportunidades" else []
            return type("R", (), {"data": dados})()

    monkeypatch.setattr(ego_notas, "get_supabase", lambda: _BD())
    novas = [{"ego_id": 1, "ref": "VEN_1", "dia": "2026-11-26", "texto": "a"},
             {"ego_id": 2, "ref": "VEN_NOVA", "dia": "2026-11-26", "texto": "b"}]
    r = ego_notas.gravar(novas, "cron")
    assert r["inseridas"] == 1 and r["sem_oportunidade"] == 1 and r["erros"] == {}
    assert [l["nota_ego_id"] for l in inseridas] == [1]
