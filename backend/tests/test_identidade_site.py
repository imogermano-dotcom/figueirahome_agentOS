"""No WhatsApp o telefone vem de graça (é o próprio `participante`); no site
não há nada a identificar quem escreve. Sem lembrete, o modelo regista
"interesse" com nome e mais nada -- e `find_or_create_cliente` (2026-09-02)
já recusa criar cliente/lead sem contacto, mas o cliente merece a pergunta
em vez de um "não consegui guardar" mudo."""

from app.agents.broker.assistants import _PROMPT_A2
from app.agents.broker.engine import (
    _data_de_hoje,
    _INSTRUCAO_IDENTIDADE_SITE,
    _INSTRUCAO_TELEFONE_WHATSAPP,
    _montar_system_prompt,
)


def test_site_ganha_a_instrucao_de_pedir_telefone():
    prompt = _montar_system_prompt({"prompt": "base"}, "", "", "site")
    assert prompt == f"base\n\n{_data_de_hoje()}" + _INSTRUCAO_IDENTIDADE_SITE


def test_whatsapp_ganha_a_instrucao_de_nao_pedir_telefone():
    """No WhatsApp perguntar o telefone é redundante -- já se sabe pelo canal.

    Antes (até 07/10) o WhatsApp não ganhava instrução nenhuma, e a Maria pediu
    "nome completo e número de telefone" a quem já escrevia do WhatsApp; medido em
    411 interacções, também a Matilde (3/39) e a Inês (3/27) o pediam. A instrução
    vai no motor, tal como a do site, e fala do número de QUEM ESCREVE (o telefone
    da agência continua a poder ser dado)."""
    prompt = _montar_system_prompt({"prompt": "base"}, "\n\nperfil", "", "whatsapp")
    assert prompt == f"base\n\nperfil\n\n{_data_de_hoje()}" + _INSTRUCAO_TELEFONE_WHATSAPP
    assert "Nunca o peças" in prompt
    assert "de quem te escreve" in prompt  # não proíbe o telefone da agência
    assert "pergunta sempre o nome E o número" not in prompt  # não é a do site


def test_site_nao_ganha_a_instrucao_do_whatsapp():
    prompt = _montar_system_prompt({"prompt": "base"}, "", "", "site")
    assert _INSTRUCAO_TELEFONE_WHATSAPP not in prompt


def test_prompt_da_maria_nao_manda_pedir_contacto_e_usa_motivos_certos():
    """Os `motivo` de escalada da Maria alimentam `scripts/monitorizar_encaminhamento.py`
    (conta `recrut|angaria|avalia|vend`); sem eles o script deixa de ver os desvios."""
    assert "recolhe\nnome e contacto" not in _PROMPT_A2
    for motivo in ('"venda"', '"avaliação"', '"recrutamento"'):
        assert motivo in _PROMPT_A2, motivo
    assert "Não sabes o género" in _PROMPT_A2
    # O menu continua intacto: `test_router.py` lê-o daqui.
    assert "apresenta as opções:\nComprar / Vender / Arrendar / Trabalhar connosco / Outro." in _PROMPT_A2


def test_painel_nao_ganha_a_instrucao():
    prompt = _montar_system_prompt({"prompt": "base"}, "", "", "web")
    assert prompt == f"base\n\n{_data_de_hoje()}"


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
