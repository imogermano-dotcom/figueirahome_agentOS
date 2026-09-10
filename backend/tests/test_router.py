"""Router de intenção — função pura, sem DB nem rede.

Corre com `pytest backend/tests/` ou directamente com
`python backend/tests/test_router.py`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker.router import A1, A2, A4, route  # noqa: E402


def test_classificacao_inicial():
    assert route("quero comprar casa", None) == A1
    assert route("procuro um T2 na Figueira até 150 mil", None) == A1
    assert route("quanto custa o FH2233?", None) == A1
    assert route("bom dia", None) == A2
    assert route("qual é o vosso horário?", None) == A2


def test_stickiness():
    # Thread já com dono e sem sinal novo — mantém-se.
    assert route("obrigado!", A1) == A1
    assert route("e onde ficam?", A1) == A1
    assert route("bom dia", A2) == A2
    # A2 -> A1 quando aparece sinal de compra.
    assert route("procuro um T2", A2) == A1


def test_a3_recrutamento_adiado_vai_para_a2():
    # A3 não existe — reconhecido, mas encaminhado para o A2.
    assert route("quero trabalhar convosco como consultor imobiliário", None) == A2
    assert route("gostaria de enviar a minha candidatura", None) == A2


def test_a4_angariacao_vai_para_barbara():
    # "casa"/"imóvel" nestas frases não pode arrastá-las para o A1.
    assert route("quero vender a minha casa", None) == A4
    assert route("quanto vale a minha casa?", None) == A4
    assert route("queria uma avaliação do meu imóvel", None) == A4
    # Stickiness: uma thread já da Bárbara mantém-se sem sinal novo.
    assert route("obrigado, fico a aguardar", A4) == A4


def test_nunca_devolve_agente_inexistente():
    conhecidos = {A1, A2, A4}
    casos = [
        ("quero comprar casa", None),
        ("bom dia", None),
        ("", None),
        ("", A1),
        ("quero vender", A1),
        ("!!!", A2),
    ]
    for mensagem, atual in casos:
        assert route(mensagem, atual) in conhecidos


if __name__ == "__main__":
    test_classificacao_inicial()
    test_stickiness()
    test_a3_recrutamento_adiado_vai_para_a2()
    test_a4_angariacao_vai_para_barbara()
    test_nunca_devolve_agente_inexistente()
    print("test_router OK")
