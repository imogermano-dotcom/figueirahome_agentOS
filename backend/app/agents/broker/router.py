"""Router de intenção — nível 1 da spec `assistentes-ia-especificacao.md` §2.2.

Decide que assistente responde. Função pura: sem DB, sem rede, sem LLM.

**Porquê regex e não uma chamada ao modelo.** O nível 1 da spec é
literalmente uma tabela de palavras-chave, e escolhe entre dois baldes, um
dos quais (`a2_geral`) está definido como "qualquer outra mensagem / não
classificada". Uma chamada extra ao modelo por cada mensagem recebida custa
latência e tokens para uma decisão cujas falhas são baratas nos dois
sentidos: keyword falhada cai no A2, cujo trabalho é justamente perceber e
encaminhar; falso A1 custa uma pergunta de qualificação que o A2 faria na
mesma. Além disso a precisão fina já está a jusante — o tool forcing do A1
(`_SEARCH_RE` em assistants.py) é que garante a pesquisa real de imóveis.

# ponytail: regex + fallback A2. Se os logs mostrarem má taxa de acerto,
# o upgrade é uma tool de classificação forçada só na 1ª mensagem da thread,
# não uma chamada por mensagem.
"""

import re

A1 = "a1_vendedor"
A2 = "a2_geral"

# Sinais de A4 (angariação) e A3 (recrutamento), da tabela §2.2. Ambos os
# assistentes estão adiados, por isso estas mensagens vão para o A2 — que
# recolhe o contacto e escala. Testados ANTES do A1 porque partilham
# vocabulário com ele ("quanto vale a minha casa" tem "casa").
_ADIADO_RE = re.compile(
    r"("
    r"quero vender|penso vender|pretendo vender|vender a minha|vender o meu|"
    r"quanto vale|aval(iar|iação|iacao)|angaria|"
    r"quero trabalhar|trabalhar convosco|consultor imobili|recrutamento|"
    r"candidatura|candidatar"
    r")",
    re.IGNORECASE,
)

# Nível 1 da tabela §2.2: intenção de compra / arrendamento / imóvel concreto.
_A1_RE = re.compile(
    r"("
    r"\b(comprar|compra|arrendar|arrendamento|alugar)|"
    r"\b(procuro|procura|interessad)|"
    r"quanto custa|\bpreç|\bpreco|orçament|orcament|"
    r"\bvisit|\bagendar|"
    r"\bt[0-9]\b|apartament|\bmorad|\bterreno|vivenda|"
    r"\bfh\s?\d+|"
    r"\bimovel|\bimóvel|\bimoveis|\bimóveis|\bcasas?\b"
    r")",
    re.IGNORECASE,
)


def route(mensagem: str, agente_atual: str | None) -> str:
    """Devolve a chave do assistente que deve responder.

    Stickiness num sentido só: A2 -> A1 quando aparece sinal de compra,
    nunca A1 -> A2. Uma thread de comprador continua thread de comprador —
    o prompt do A1 cobre perguntas institucionais soltas sem precisar de
    devolver a conversa ao A2 e perder o contexto de qualificação.

    A3 (recrutamento) e A4 (angariação) estão fora do âmbito desta fase:
    são reconhecidos, mas encaminhados para o A2 — deixar o A2 recolher o
    contacto e escalar é melhor do que rotear para um assistente que não
    existe. É também por isso que este teste vem primeiro: "quanto vale a
    minha casa" é angariação, não compra, apesar de conter "casa".
    """
    texto = mensagem or ""
    if _ADIADO_RE.search(texto):
        return A2
    if _A1_RE.search(texto):
        return A1
    if agente_atual:
        return agente_atual
    return A2


def demo() -> None:
    """`python -m app.agents.broker.router`"""
    assert route("quero comprar casa", None) == A1
    assert route("bom dia", None) == A2
    assert route("obrigado!", A1) == A1
    assert route("procuro um T2", A2) == A1
    assert route("quero vender a minha casa", None) == A2
    print("router OK")


if __name__ == "__main__":
    demo()
