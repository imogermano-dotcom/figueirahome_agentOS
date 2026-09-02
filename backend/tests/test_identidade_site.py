"""No WhatsApp o telefone vem de graça (é o próprio `participante`); no site
não há nada a identificar quem escreve. Sem lembrete, o modelo regista
"interesse" com nome e mais nada -- e `find_or_create_cliente` (2026-09-02)
já recusa criar cliente/lead sem contacto, mas o cliente merece a pergunta
em vez de um "não consegui guardar" mudo."""

from app.agents.broker.engine import _INSTRUCAO_IDENTIDADE_SITE, _montar_system_prompt


def test_site_ganha_a_instrucao_de_pedir_telefone():
    prompt = _montar_system_prompt({"prompt": "base"}, "", "", "site")
    assert prompt == "base" + _INSTRUCAO_IDENTIDADE_SITE


def test_whatsapp_nao_ganha_a_instrucao():
    """No WhatsApp perguntar o telefone é redundante -- já se sabe pelo canal."""
    prompt = _montar_system_prompt({"prompt": "base"}, "\n\nperfil", "", "whatsapp")
    assert "telefone" not in prompt.lower()
    assert prompt == "base\n\nperfil"


def test_painel_nao_ganha_a_instrucao():
    prompt = _montar_system_prompt({"prompt": "base"}, "", "", "web")
    assert prompt == "base"


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
