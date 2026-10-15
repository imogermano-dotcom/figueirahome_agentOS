"""`tarefa_criado_em` do relatório "todas as colunas" tem de chegar à base em ISO.

15/10: o sync de oportunidades gravou tudo menos as tarefas ("date/time field value out of range:
15/07/2026", 325 registos por gravar) porque a coluna `date` recebia o "dd/mm/aaaa" cru do relatório.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scraper"))

import mapping_todas_colunas as m  # noqa: E402


def _tarefa(criado):
    registo = {"tarefa_status": "Pendente", "tarefa_titulo": "Ligar", "tarefa_due_raw": "20/07/2026"}
    if criado is not None:
        registo["tarefa_criado_em"] = criado
    return m.classify(registo)["tarefa"]


@pytest.mark.parametrize("cru, iso", [("15/07/2026", "2026-07-15"), ("03/07/2026", "2026-07-03")])
def test_criado_em_vai_em_iso_e_sem_trocar_dia_e_mes(cru, iso):
    assert _tarefa(cru)["tarefa_criado_em"] == iso  # "03/07" é 3 de julho, nunca 7 de março


def test_data_ilegivel_nao_rebenta_o_lote():
    assert "tarefa_criado_em" not in _tarefa("ontem")


def test_sem_data_continua_sem_a_chave():
    assert "tarefa_criado_em" not in _tarefa(None)


def test_as_outras_datas_da_tarefa_continuam_convertidas():
    assert _tarefa("15/07/2026")["tarefa_due_iso"] == "2026-07-20"


# ── estado da tarefa: o enum da base só aceita 'pendente'/'concluida' (15/10) ──

@pytest.mark.parametrize("cru, esperado", [
    ("Concluído", "concluida"), ("Pendente", "pendente"), ("Em Curso", "pendente"),
])
def test_estado_da_tarefa_sai_no_vocabulario_do_enum(cru, esperado):
    registo = {"tarefa_status": cru, "tarefa_titulo": "Ligar"}
    assert m.classify(registo)["tarefa"]["tarefa_status"] == esperado


def test_mesmo_vocabulario_do_sync_de_tarefas():
    import tarefas

    assert m._ESTADO_TAREFA == tarefas._ESTADOS
