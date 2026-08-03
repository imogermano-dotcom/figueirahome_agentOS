"""Markdown → WhatsApp. Função pura, sem DB nem rede.

    python backend/tests/test_formatacao_whatsapp.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker.channels.whatsapp.formatacao import para_whatsapp  # noqa: E402


def test_negrito():
    # O WhatsApp usa asterisco simples; asterisco duplo aparece literal.
    assert para_whatsapp("O **FH2550** custa **270.000€**") == "O *FH2550* custa *270.000€*"
    assert para_whatsapp("__importante__") == "*importante*"
    assert para_whatsapp("sem formatação") == "sem formatação"


def test_titulos():
    assert para_whatsapp("## Ficha do imóvel") == "*Ficha do imóvel*"
    assert para_whatsapp("### T3 Remodelado") == "*T3 Remodelado*"


def test_regua_desaparece_mas_bullets_sobrevivem():
    assert para_whatsapp("antes\n---\ndepois") == "antes\n\ndepois"
    # Um bullet começa por "- " e não é uma régua — não pode ser apagado.
    assert para_whatsapp("- piscina\n- garagem") == "- piscina\n- garagem"


def test_links():
    assert para_whatsapp("[ver fotos](https://x.pt/a)") == "ver fotos: https://x.pt/a"


def test_tabela_da_ficha_real():
    """O caso que chegou a um cliente como um bloco de | e ---."""
    entrada = (
        "*FH2550 — T3 com Garagem*\n"
        "\n"
        "| | |\n"
        "|---|---|\n"
        "| 📐 Área útil | 102 m² |\n"
        "| 🛏️ Tipologia | T3 |\n"
        "| 🚗 Garagem | Incluída |\n"
    )
    saida = para_whatsapp(entrada)
    assert "|" not in saida, saida
    assert "---" not in saida, saida
    assert "📐 Área útil: 102 m²" in saida
    assert "🛏️ Tipologia: T3" in saida
    assert "🚗 Garagem: Incluída" in saida


def test_tabela_de_tres_colunas():
    entrada = "| Ref | Tipo | Preço |\n|---|---|---|\n| FH2542 | Moradia | 65.000€ |"
    saida = para_whatsapp(entrada)
    assert "FH2542 · Moradia · 65.000€" in saida
    assert "|" not in saida


def test_vazio_e_nulo():
    assert para_whatsapp("") == ""
    assert para_whatsapp(None) is None


def test_mensagem_normal_fica_intacta():
    texto = "Boa tarde! Encontrei 3 imóveis na Figueira da Foz. Qual lhe interessa?"
    assert para_whatsapp(texto) == texto


if __name__ == "__main__":
    for nome, fn in list(globals().items()):
        if nome.startswith("test_"):
            fn()
            print(f"  ok  {nome}")
    print("test_formatacao_whatsapp OK")
