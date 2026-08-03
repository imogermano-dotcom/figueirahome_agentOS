"""Markdown → formatação do WhatsApp.

O modelo escreve Markdown por defeito e o WhatsApp não o percebe: usa asterisco
**simples** para negrito e **não tem tabelas**. Confirmado numa conversa real em
produção — a ficha do imóvel FH2550 chegou ao cliente como um bloco de `|` e
`---`.

A conversão vive aqui, no único ponto de saída para o WhatsApp, e não no prompt:
uma instrução no prompt é uma sugestão que o modelo esquece a meio de uma ficha
longa; isto é determinístico. O prompt continua a pedir texto simples — as duas
coisas somam, não competem.
"""

import re

# **negrito** e __negrito__ -> *negrito* (o WhatsApp usa asterisco simples)
_NEGRITO = re.compile(r"\*\*(.+?)\*\*|__(.+?)__", re.DOTALL)

# ## Título -> *Título*
_TITULO = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", re.MULTILINE)

# Linha horizontal --- *** ___ sozinha: não existe no WhatsApp, desaparece.
# Exige 3+ e nada mais na linha, por isso não apanha bullets "- item".
_REGUA = re.compile(r"^[ \t]*([-*_])\1{2,}[ \t]*$", re.MULTILINE)

# [texto](url) -> texto: url  (o WhatsApp já transforma URLs em links)
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")

# Linha de separador de tabela: |---|:--:|
_TABELA_SEP = re.compile(r"^\s*\|[\s:|-]+\|\s*$")

_TRES_LINHAS_VAZIAS = re.compile(r"\n{3,}")


def _celulas(linha: str) -> list[str]:
    """Parte uma linha de tabela nas suas células não vazias."""
    return [c.strip() for c in linha.strip().strip("|").split("|") if c.strip()]


def _converter_tabelas(texto: str) -> str:
    """Achata tabelas Markdown em linhas `rótulo: valor`.

    Duas colunas viram `rótulo: valor` — é a forma que as fichas de imóvel usam.
    Mais colunas juntam-se com ` · `. Uma célula só fica como está.
    """
    saida = []
    for linha in texto.split("\n"):
        if not linha.strip().startswith("|"):
            saida.append(linha)
            continue
        if _TABELA_SEP.match(linha):
            continue  # |---|---| não tem equivalente
        celulas = _celulas(linha)
        if not celulas:
            continue  # linha de tabela vazia: | | |
        saida.append(celulas[0] if len(celulas) == 1 else
                     f"{celulas[0]}: {celulas[1]}" if len(celulas) == 2 else
                     " · ".join(celulas))
    return "\n".join(saida)


def para_whatsapp(texto: str) -> str:
    if not texto:
        return texto

    texto = _converter_tabelas(texto)
    texto = _TITULO.sub(r"*\1*", texto)
    texto = _REGUA.sub("", texto)
    texto = _LINK.sub(r"\1: \2", texto)
    # Um dos dois grupos casa; o outro vem None.
    texto = _NEGRITO.sub(lambda m: f"*{m.group(1) or m.group(2)}*", texto)
    texto = _TRES_LINHAS_VAZIAS.sub("\n\n", texto)
    return texto.strip()
