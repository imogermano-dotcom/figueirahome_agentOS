"""Contagem de falhas seguidas do uptime check — função pura, sem DB nem rede.

Corre com `pytest backend/tests/` ou directamente com
`python backend/tests/test_site_uptime.py`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.site_uptime import _contar_falhas_no_topo, _historico_ok, _LIMIAR_FALHAS  # noqa: E402


def test_conta_falhas_a_partir_do_topo():
    assert _contar_falhas_no_topo([False, False, False, True]) == 3
    assert _contar_falhas_no_topo([True, False, False]) == 0
    assert _contar_falhas_no_topo([False]) == 1
    assert _contar_falhas_no_topo([]) == 0
    assert _contar_falhas_no_topo([False, False]) == 2


def test_so_alerta_exactamente_ao_atingir_o_limiar():
    # Simula o que `verificar_site` vê a cada execução: o topo é a mais recente.
    assert _contar_falhas_no_topo([False, False, False]) == _LIMIAR_FALHAS  # dispara
    assert _contar_falhas_no_topo([False, False, False, False]) != _LIMIAR_FALHAS  # já alertou, não repete


def test_recuperacao_so_conta_se_ja_tinha_alertado():
    historico_apos_sucesso = [True, False, False, False]  # sucesso agora, 3 falhas antes
    assert _contar_falhas_no_topo(historico_apos_sucesso[1:]) >= _LIMIAR_FALHAS

    historico_sem_alerta_previo = [True, False, False]  # só 2 falhas antes — nunca alertou
    assert _contar_falhas_no_topo(historico_sem_alerta_previo[1:]) < _LIMIAR_FALHAS


def test_historico_ok_tolera_resumo_vazio():
    linhas = [{"resumo": {"ok": True}}, {"resumo": {"ok": False}}, {"resumo": None}, {}]
    assert _historico_ok(linhas) == [True, False, False, False]


if __name__ == "__main__":
    test_conta_falhas_a_partir_do_topo()
    test_so_alerta_exactamente_ao_atingir_o_limiar()
    test_recuperacao_so_conta_se_ja_tinha_alertado()
    test_historico_ok_tolera_resumo_vazio()
    print("test_site_uptime OK")
