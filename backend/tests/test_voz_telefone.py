"""Voz: o telefone é o da chamada, não o que o STT ouviu (`claude_agent.instrucao_telefone`, `save_call.telefone_da_chamada`).

Corre com `pytest backend/tests/` ou `python backend/tests/test_voz_telefone.py`. Sem rede nem credenciais.
Caso real de 17/10: a assistente pedia o telefone dígito a dígito («qual é o dígito que falta no final?») a quem tinha dito
sete dos nove, e o número gravado seria o truncado.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.voice import claude_agent, save_call  # noqa: E402


@pytest.mark.parametrize("origem", ["+351912345678", "00351912345678", "912345678", "351912345678"])
def test_com_numero_da_chamada_a_assistente_nao_o_pede(origem):
    t = claude_agent.instrucao_telefone(origem)
    assert "já é conhecido" in t and "nunca o peças" in t
    assert "um dígito isolado" in t, "e nunca pede dígitos soltos"


@pytest.mark.parametrize("origem", [None, "", "anonymous", "desconhecido", "12345"])
def test_chamada_anonima_pede_o_numero_completo_de_uma_vez(origem):
    t = claude_agent.instrucao_telefone(origem)
    assert "não mostra o número" in t and "de uma só vez" in t
    assert "nunca peças um dígito isolado" in t


def test_o_prompt_base_ja_nao_manda_pedir_digito_a_digito():
    assert "dígito a dígito" not in claude_agent._SYSTEM_BASE
    assert "Número de telefone de contacto" not in claude_agent._SYSTEM_BASE


def test_numero_dito_truncado_nao_substitui_o_da_chamada():
    assert save_call.telefone_da_chamada("9159025", "+351912345678") == "+351912345678"
    assert save_call.telefone_da_chamada(None, "+351912345678") == "+351912345678"
    assert save_call.telefone_da_chamada("", "+351912345678") == "+351912345678"


def test_numero_dito_completo_e_diferente_substitui_o_da_chamada():
    assert save_call.telefone_da_chamada("933 444 555", "+351912345678") == "933 444 555"


def test_numero_dito_igual_ao_da_chamada_fica_o_da_chamada():
    assert save_call.telefone_da_chamada("912 345 678", "+351912345678") == "+351912345678"


def test_sem_numero_da_chamada_usa_o_dito_se_completo():
    assert save_call.telefone_da_chamada("912345678", None) == "912345678"
    assert save_call.telefone_da_chamada("9159025", None) is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
