import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from fechar_tarefas_legadas import a_fechar, classificar


def _t(id, ref, titulo="Contactar", due="01/10/2026", origem="Ativas", ego_id=None):
    return {"id": id, "oportunidade_ref": ref, "tarefa_titulo": titulo, "tarefa_due_raw": due, "origem_lista": origem, "ego_id": ego_id}


def test_classifica_a_b_c_e_nunca_toca_nas_vivas():
    vivas = [_t(100, "VEN_2", due="05/12/2026", origem="todas_as_colunas", ego_id=9),
             _t(101, "VEN_3", due="Hoje, 10:54", origem="todas_as_colunas", ego_id=8)]
    legadas = [_t(1, "VEN_1"),                       # A: oportunidade sem pendentes na API
               _t(2, "VEN_3", due="Hoje, 10:54"),    # B: mesma chave viva
               _t(3, "VEN_2"),                       # C: oportunidade com pendentes, esta não aparece
               _t(4, "VEN_2", due="06/12/2026"),     # C
               _t(5, "VEN_1", ego_id=7),             # tem ego_id: ignorada
               _t(6, "VEN_1", origem="todas_as_colunas")]  # não é legada
    r = classificar(legadas, vivas)
    assert [t["id"] for t in r["A"]] == [1] and [t["id"] for t in r["B"]] == [2] and [t["id"] for t in r["C"]] == [3, 4]
    assert r["c_mesmo_titulo"] == 2
    assert [t["id"] for t in a_fechar(r, False)] == [1, 2]
    assert [t["id"] for t in a_fechar(r, True)] == [1, 2, 3, 4]
