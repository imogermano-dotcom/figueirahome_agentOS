"""Router de intenção — função pura, sem DB nem rede.

Corre com `pytest backend/tests/` ou directamente com
`python backend/tests/test_router.py`.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker.assistants import _PROMPT_A2  # noqa: E402
from app.agents.broker.router import A1, A2, A3, A4, route  # noqa: E402


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


def test_a3_recrutamento_vai_para_ines():
    assert route("quero trabalhar convosco como consultor imobiliário", None) == A3
    assert route("gostaria de enviar a minha candidatura", None) == A3
    # Stickiness: uma thread já da Inês mantém-se sem sinal novo.
    assert route("obrigado, fico a aguardar", A3) == A3


def test_a4_angariacao_vai_para_barbara():
    # "casa"/"imóvel" nestas frases não pode arrastá-las para o A1.
    assert route("quero vender a minha casa", None) == A4
    assert route("quanto vale a minha casa?", None) == A4
    assert route("queria uma avaliação do meu imóvel", None) == A4
    # Stickiness: uma thread já da Bárbara mantém-se sem sinal novo.
    assert route("obrigado, fico a aguardar", A4) == A4


def test_a3_a4_nao_saltam_para_a1_a_meio_da_conversa():
    # Bug real (20/09): "imóveis"/"visita"/"preço" batem em _A1_RE e uma
    # thread já da Inês ou da Bárbara saltava para o A1 sem aviso.
    assert route("sempre gostei de imóveis, full-time", A3) == A3
    assert route("qual é o preço da visita de avaliação?", A4) == A4
    assert route("quanto custa a formação?", A3) == A3


def test_nunca_devolve_agente_inexistente():
    conhecidos = {A1, A2, A3, A4}
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


# Destino esperado de cada opção do menu que a Maria apresenta. O menu é a
# interface com o utilizador: se uma opção nova aparecer no prompt sem entrada
# aqui, o teste falha de propósito (achado 07/10: "Trabalhar" ficava na A2).
_DESTINO_MENU = {
    "comprar": A1,
    "vender": A4,
    "arrendar": A1,
    "trabalhar connosco": A3,
    "outro": A2,
}


def _opcoes_do_menu_da_a2() -> list[str]:
    m = re.search(r"apresenta as opções:\s*([^\n]+?)\.", _PROMPT_A2)
    assert m, "menu da A2 não encontrado em _PROMPT_A2 — o teste tem de acompanhar o prompt"
    return [o.strip() for o in m.group(1).split("/")]


def test_menu_da_a2_encaminha_cada_opcao():
    opcoes = _opcoes_do_menu_da_a2()
    assert len(opcoes) >= 4, opcoes
    for opcao in opcoes:
        esperado = _DESTINO_MENU.get(opcao.lower())
        assert esperado, f"opção nova no menu da A2 sem destino no teste: {opcao!r}"
        # A resposta tal como o menu a escreve, só com a 1.ª palavra (como a pessoa
        # responde) e em minúsculas.
        for texto in (opcao, opcao.split()[0], opcao.lower(), opcao.upper() + "!"):
            assert route(texto, A2) == esperado, (texto, route(texto, A2), esperado)


def test_variantes_de_recrutamento_e_angariacao():
    for frase in ("Trabalhar", "quero trabalhar na vossa agência", "trabalhar com vocês",
                  "gostava de trabalhar connosco", "procuro emprego na imobiliária",
                  "queria fazer parte da vossa equipa"):
        assert route(frase, A2) == A3, frase
    for frase in ("Vender", "vender um apartamento", "vender imóvel", "quero vender"):
        assert route(frase, A2) == A4, frase


def test_palavras_vizinhas_nao_desviam_compradores():
    # Mesmo vocabulário, outra intenção: nunca para a Inês nem para a Bárbara.
    assert route("tenho emprego estável e quero comprar casa", A2) == A1
    assert route("trabalho de casa, procuro um T2", A2) == A1
    assert route("preciso de um T3 para trabalhar de casa", A2) == A1
    assert route("trabalhar", A1) == A1  # thread já da Matilde: sticky, sem regex
    assert route("podem vender-me algo na zona?", None) == A2


if __name__ == "__main__":
    test_classificacao_inicial()
    test_stickiness()
    test_a3_recrutamento_vai_para_ines()
    test_a4_angariacao_vai_para_barbara()
    test_a3_a4_nao_saltam_para_a1_a_meio_da_conversa()
    test_nunca_devolve_agente_inexistente()
    test_menu_da_a2_encaminha_cada_opcao()
    test_variantes_de_recrutamento_e_angariacao()
    test_palavras_vizinhas_nao_desviam_compradores()
    print("test_router OK")
