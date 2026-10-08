"""Turno sem texto depois de escalar não pode mostrar "Ocorreu um erro" (08/10)."""

from app.agents.broker.engine import _ERRO, _RESPOSTA_ESCALADA, _sem_erro_apos_escalar


def test_sem_texto_depois_de_escalar_responde_com_frase_fixa():
    assert _sem_erro_apos_escalar(_ERRO, ["guardar_dados_cliente", "escalar_para_humano"]) == _RESPOSTA_ESCALADA


def test_erro_sem_escalada_mantem_se():
    assert _sem_erro_apos_escalar(_ERRO, ["guardar_dados_cliente"]) == _ERRO


def test_texto_do_modelo_nunca_e_substituido():
    assert _sem_erro_apos_escalar("Até breve!", ["escalar_para_humano"]) == "Até breve!"
