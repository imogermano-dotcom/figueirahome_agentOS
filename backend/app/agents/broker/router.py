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
A3 = "a3_recrutamento"
A4 = "a4_angariador"

# Sinais de angariação (venda/arrendamento do PRÓPRIO imóvel) — vão para a
# Bárbara (A4). Testados ANTES do A1 porque partilham vocabulário com ele
# ("quanto vale a minha casa" tem "casa").
_A4_RE = re.compile(
    r"("
    r"quero vender|penso vender|pretendo vender|vender a minha|vender o meu|"
    r"quanto vale|aval(iar|iação|iacao)|angaria"
    r")",
    re.IGNORECASE,
)

# Sinais de A3 (recrutamento), da tabela §2.2 — Inês.
_A3_RE = re.compile(
    r"("
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

    Stickiness num sentido só, a sério: A2 -> A1/A3/A4 quando aparece o sinal
    correspondente, nunca o inverso, e nunca entre A1/A3/A4 uma vez atribuída
    — o prompt de cada assistente cobre perguntas institucionais soltas sem
    devolver a conversa ao A2 e perder o contexto de qualificação.

    Bug real (20/09, achado a testar a Inês): a thread já tinha `_A3_RE`
    atribuído, mas a mensagem seguinte ("sempre gostei de imóveis...") batia
    em `_A1_RE` (que reconhece "imóveis", "preço", "visita" — vocabulário
    normal numa conversa de recrutamento OU de angariação) e devolvia A1 a
    meio da conversa, sem aviso. O `if agente_atual` só protegia contra a
    ausência de qualquer sinal, nunca contra um sinal de OUTRO balde. Como a
    Bárbara (A4) já está em produção, o mesmo podia acontecer com ela — um
    proprietário a dizer "o imóvel tem 3 quartos" a meio de uma angariação.
    Por isso a stickiness de A1/A3/A4 corre ANTES de qualquer regex.
    """
    texto = mensagem or ""
    if agente_atual and agente_atual != A2:
        return agente_atual
    if _A3_RE.search(texto):
        return A3
    if _A4_RE.search(texto):
        return A4
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
    assert route("quero vender a minha casa", None) == A4
    assert route("quero trabalhar convosco", None) == A3
    print("router OK")


if __name__ == "__main__":
    demo()
