"""O template inicial da Meta — o que os fluxos `01` e `02` do n8n mandam.

Estes testes não correm o n8n; lêem os JSON em `docs/n8n/` e verificam as três
coisas que já falharam ou que a Cloud API recusa em silêncio:

1. **`01` e `02` têm de dizer exactamente o mesmo.** São o mesmo template
   aprovado por dois caminhos (webhook e backfill). Divergirem faz o backfill
   mandar texto antigo, e o texto gravado em `leads.template_enviado` deixa de
   ser o que a pessoa recebeu.
2. **O texto nomeia a Matilde.** `engine.py:147` faz
   `if NOME_A1.lower() in template.lower()` sobre o texto gravado para decidir
   se a A1 se volta a apresentar. Tirar o nome daqui põe-na a dizer "Sou a
   Matilde" logo a seguir a uma mensagem que já o dizia.
3. **Nenhum parâmetro sai vazio nem leva quebras de linha.** A Cloud API recusa
   parâmetros vazios e parâmetros com `\\n`, `\\r`, tab ou mais de 4 espaços
   seguidos — daí `imoveis.descricao` (1100-1300 caracteres, com `\\r\\n` lá
   dentro) não poder ir, e o título ir no lugar dela.

Corre com `pytest backend/tests/` ou `python backend/tests/test_template_meta.py`.
"""

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker.assistants import APRESENTACAO_A1, NOME_A1  # noqa: E402

N8N = Path(__file__).resolve().parents[2] / "docs" / "n8n"

# A Meta recusa o parâmetro; não corta nem normaliza. O nó aborta e a lead fica
# por marcar, a ser reapanhada na corrida seguinte.
_PROIBIDO_NO_PARAMETRO = re.compile(r"[\n\r\t]|    ")

_LIMITE_CORPO = 1024
_FALLBACK_NOME = "boa tarde"
_FALLBACK_IMOVEL = "um imóvel na Figueira da Foz"

# Aprovado na Meta a 2026-08-28.
_NOME_TEMPLATE = "figueirahome_apos_lead"


def _fluxo(nome: str) -> dict:
    return json.loads((N8N / nome).read_text(encoding="utf-8"))


def _no(fluxo: dict, nome: str) -> dict:
    return next(n for n in fluxo["nodes"] if n["name"] == nome)


def _texto(nome_do_ficheiro: str) -> str:
    atribuicoes = _no(_fluxo(nome_do_ficheiro), "Preparar texto e número")
    valores = atribuicoes["parameters"]["assignments"]["assignments"]
    return next(a["value"] for a in valores if a["name"] == "texto_renderizado")


_MAX_TITULO = 120


def _composto(imovel: dict) -> str:
    """A rede: campos estruturados, quando não há título."""
    val = lambda chave: imovel.get(chave) or None  # noqa: E731
    tipo = " ".join(
        x for x in (imovel.get("natureza"), f"T{imovel['quartos']}" if val("quartos") else None) if x
    )
    area = val("area_util") or val("area_bruta") or val("area_terreno")
    zona = re.sub(
        r"\s+d[ae]\s+Figueira da Foz$", "", str(imovel.get("freguesia") or ""), flags=re.I
    ).strip()
    preco = val("venda_preco") or val("arrendamento_preco")
    euros = f"{preco:,}".replace(",", " ") + " €" if preco else None
    return ", ".join(x for x in (tipo, f"{area} m²" if area else None, zona, euros) if x)


def _resumo(imovel: dict) -> str:
    """Espelho em Python do nó de código `Resumo do imóvel`.

    Mantido honesto por `test_o_espelho_do_resumo_bate_certo_com_o_no_de_codigo`
    e pelo cruzamento com o JavaScript real. O `or None` do `_composto` reproduz
    o `||` do JavaScript, onde `0` é falso — é o que faz `area_util = 0` cair
    para a `area_bruta` e `quartos = 0` não virar "T0".
    """
    titulo = re.sub(r"\s+", " ", str(imovel.get("titulo") or "")).strip()
    return titulo if titulo and len(titulo) <= _MAX_TITULO else _composto(imovel)


def _render(nome: str | None, ref: str | None, resumo: str | None) -> tuple[str, str, str]:
    """Espelho em Python das expressões do nó `Preparar texto e número`.

    Duplicação assumida: o n8n não corre aqui. O que a mantém honesta é
    `test_o_espelho_bate_certo_com_o_texto_do_n8n`, que compara os dois.
    """
    p1 = (nome or "").strip().split(" ")[0] or _FALLBACK_NOME
    p2 = " — ".join(x for x in (ref, resumo) if x) or _FALLBACK_IMOVEL
    corpo = (
        f"Olá {p1},\n"
        f"{APRESENTACAO_A1}\n"
        "Recebemos o seu interesse, através das redes sociais, no seguinte imóvel:\n"
        f"{p2}\n"
        "Posso ajudar com alguma informação?"
    )
    return p1, p2, corpo


# ── o texto ───────────────────────────────────────────────────────────


def test_os_dois_fluxos_mandam_o_mesmo_texto():
    a, b = _texto("01-enviar-template.json"), _texto("02-backfill-template.json")
    # Só diferem em de onde lêem a lead: o `01` vem do nó que a foi buscar, o
    # `02` do item do ciclo. A frase tem de ser a mesma.
    normaliza = lambda t: (  # noqa: E731
        t.replace("$('Ler lead no Supabase')", "«lead»").replace("$('Uma de cada vez')", "«lead»")
    )
    assert normaliza(a) == normaliza(b)


@pytest.mark.parametrize("ficheiro", ["01-enviar-template.json", "02-backfill-template.json"])
def test_o_texto_nomeia_a_matilde(ficheiro):
    """A condição literal de `engine.py:147`."""
    assert NOME_A1.lower() in _texto(ficheiro).lower()


@pytest.mark.parametrize("ficheiro", ["01-enviar-template.json", "02-backfill-template.json"])
def test_o_texto_tem_os_dois_fallbacks(ficheiro):
    texto = _texto(ficheiro)
    assert _FALLBACK_NOME in texto
    assert _FALLBACK_IMOVEL in texto, "sem isto, uma ref fora da `imoveis` manda parâmetro vazio"


# ── o resumo do imóvel ────────────────────────────────────────────────
#
# **Não há coluna de resumo na `imoveis`** — procurada nas 64. Usa-se o `titulo`,
# que é o que a agência escreveu para identificar o imóvel e diz coisas que
# nenhum campo estruturado sabe ("T3+1 duplex com jardim privativo e vistas de
# mar"). Quando falta — 1 dos 54 —, compõe-se um dos campos estruturados.
#
# A `descricao` não serve nem como rede: 1100-1300 caracteres com quebras de
# linha a sério, e a Meta **rejeita** parâmetros com quebras de linha.

_FH2572 = {
    "titulo": "T4 na cidade em excelente estado com garagem",
    "natureza": "Apartamento", "quartos": 4, "area_util": 130, "area_bruta": 150,
    "area_terreno": 0, "freguesia": "São Julião da Figueira da Foz",
    "venda_preco": 313000, "arrendamento_preco": None,
}
_SEM_TITULO = {**_FH2572, "titulo": None}


@pytest.mark.parametrize("ficheiro", ["01-enviar-template.json", "02-backfill-template.json"])
def test_o_no_de_codigo_le_os_campos_que_usa(ficheiro):
    fluxo = _fluxo(ficheiro)
    consulta = json.dumps(_no(fluxo, "Ler imóvel")["parameters"], ensure_ascii=False)
    for campo in _FH2572:
        assert campo in consulta, f"`{campo}` fora do `select` — sai sempre vazio do nó"
    codigo = _no(fluxo, "Resumo do imóvel")["parameters"]
    assert codigo["mode"] == "runOnceForEachItem", "no modo por lote, `$json` é o primeiro item"
    assert "return { json: { resumo } }" in codigo["jsCode"]


@pytest.mark.parametrize("ficheiro", ["01-enviar-template.json", "02-backfill-template.json"])
def test_o_espelho_do_resumo_bate_certo_com_o_no_de_codigo(ficheiro):
    """Se o JavaScript mudar e o espelho não, os testes abaixo passam a medir
    outra coisa. Verificam-se os pedaços que não podem cair."""
    js = _no(_fluxo(ficheiro), "Resumo do imóvel")["parameters"]["jsCode"]
    assert f"const MAX_TITULO = {_MAX_TITULO};" in js
    assert "titulo && titulo.length <= MAX_TITULO ? titulo : composto" in js
    assert r"replace(/\s+/g, ' ')" in js, "título sem achatar faz a Meta recusar o parâmetro"
    assert "'T' + $json.quartos" in js
    assert "n($json.area_util) || n($json.area_bruta) || n($json.area_terreno)" in js
    assert "Figueira da Foz$" in js, "sem isto a freguesia repete o concelho"
    assert r"replace(/\B(?=(\d{3})+(?!\d))/g, ' ')" in js, "preço sem separador de milhares"


@pytest.mark.parametrize("ficheiro", ["01-enviar-template.json", "02-backfill-template.json"])
def test_o_no_de_codigo_e_igual_nos_dois_fluxos(ficheiro):
    outro = "02-backfill-template.json" if ficheiro.startswith("01") else "01-enviar-template.json"
    assert (
        _no(_fluxo(ficheiro), "Resumo do imóvel")["parameters"]["jsCode"]
        == _no(_fluxo(outro), "Resumo do imóvel")["parameters"]["jsCode"]
    )


def test_o_titulo_ganha_quando_existe():
    """Diz coisas que nenhum campo estruturado sabe — "T3+1 duplex", "vista de
    mar", "pronto a habitar"."""
    assert _resumo(_FH2572) == "T4 na cidade em excelente estado com garagem"
    assert _resumo({**_FH2572, "titulo": "T3+1 duplex com jardim privativo e vistas de mar"}) == (
        "T3+1 duplex com jardim privativo e vistas de mar"
    )


def test_o_composto_e_a_rede_quando_nao_ha_titulo():
    assert _resumo(_SEM_TITULO) == "Apartamento T4, 130 m², São Julião, 313 000 €"
    assert _resumo({**_FH2572, "titulo": "   "}) == _resumo(_SEM_TITULO), "branco não é título"


def test_titulo_comprido_de_mais_cai_para_a_rede():
    """Máximo observado nos 54: 101 caracteres. Acima de 120 deixa de identificar
    e passa a ser parágrafo — aí vale mais a rede, que é sempre curta."""
    assert _resumo({**_FH2572, "titulo": "x" * _MAX_TITULO}) == "x" * _MAX_TITULO
    assert _resumo({**_FH2572, "titulo": "x" * (_MAX_TITULO + 1)}) == _resumo(_SEM_TITULO)


def test_o_titulo_e_achatado_antes_de_ser_usado():
    """A Meta recusa parâmetros com quebras de linha, tabs ou mais de 4 espaços
    seguidos — recusa, não corta. É o que tira a `descricao` de cima da mesa, e o
    que protege de um título com um newline colado pelo backoffice."""
    r = _resumo({**_FH2572, "titulo": "T2 no centro\r\n  com    terraço"})
    assert r == "T2 no centro com terraço"
    assert not _PROIBIDO_NO_PARAMETRO.search(r)
    assert not _PROIBIDO_NO_PARAMETRO.search(_resumo(_SEM_TITULO))


def test_terreno_nao_ganha_tipologia_inventada():
    """17 dos 54 não têm `quartos`: 12 terrenos, 1 lote, 1 armazém e 2 prédios de
    investimento. Zero apartamentos ou moradias — omitir o T é seguro."""
    terreno = {**_SEM_TITULO, "natureza": "Terreno", "quartos": None,
               "area_util": 0, "area_bruta": 0, "area_terreno": 3045,
               "freguesia": "Lavos", "venda_preco": 97000}
    assert _resumo(terreno) == "Terreno, 3045 m², Lavos, 97 000 €"
    assert "T0" not in _resumo({**terreno, "quartos": 0})


def test_a_area_cai_de_util_para_bruta_e_depois_terreno():
    """`area_util` está a zero em 26 dos 54; `area_bruta` recupera 15."""
    assert "150 m²" in _resumo({**_SEM_TITULO, "area_util": 0})
    assert "9 m²" in _resumo({**_SEM_TITULO, "area_util": 0, "area_bruta": 0, "area_terreno": 9})


def test_a_freguesia_nao_repete_o_concelho():
    """A frase anterior já disse Figueira da Foz. As outras oito freguesias
    (Buarcos, Lavos, Quiaios…) não têm sufixo e ficam intactas."""
    assert "São Julião," in _resumo(_SEM_TITULO)
    assert "Figueira da Foz" not in _resumo(_SEM_TITULO)
    assert "Buarcos," in _resumo({**_SEM_TITULO, "freguesia": "Buarcos"})


def test_o_preco_leva_separador_de_milhares():
    assert "313 000 €" in _resumo(_SEM_TITULO)
    assert "1 250 000 €" in _resumo({**_SEM_TITULO, "venda_preco": 1250000})
    # Arrendamento: `arrendamento_preco` está vazio nos 54 publicados hoje, mas
    # o tipo de lead existe e o dia em que aparecer não pode sair sem preço.
    assert "750 €" in _resumo({**_SEM_TITULO, "venda_preco": None, "arrendamento_preco": 750})


def test_o_imovel_sem_titulo_nem_descricao_tem_resumo_na_mesma():
    """O FH2298 não tem nem título nem descrição — é o único dos 54, e era o
    buraco de qualquer abordagem baseada em prosa."""
    fh2298 = {**_SEM_TITULO, "natureza": "Moradia", "quartos": 8, "area_util": 474,
              "venda_preco": 480000}
    assert _resumo(fh2298) == "Moradia T8, 474 m², São Julião, 480 000 €"


def test_sem_campo_nenhum_sobra_o_fallback_do_parametro():
    """Um imóvel sem nada sai vazio deste nó, e quem trata do vazio é o `{{2}}`
    — a Cloud API recusa parâmetro vazio."""
    assert _resumo({}) == ""
    assert _render("Ana", None, _resumo({}))[1] == _FALLBACK_IMOVEL


@pytest.mark.parametrize("ficheiro", ["01-enviar-template.json", "02-backfill-template.json"])
def test_o_espelho_bate_certo_com_o_texto_do_n8n(ficheiro):
    """Se o texto mudar no n8n e não aqui, o resto do ficheiro passa a testar
    uma frase que já ninguém envia."""
    sem_variaveis = re.sub(r"\{\{.*?\}\}", "\x00", _texto(ficheiro)).lstrip("=")
    assert sem_variaveis == _render("\x00", "\x00", None)[2]


# ── os parâmetros ─────────────────────────────────────────────────────


def test_o_corpo_do_no_01_continua_a_ser_json_valido():
    """O `01` monta o pedido à mão. Os dois parâmetros saem por
    `JSON.stringify(...)`, que já traz as aspas — daí **não** haver aspas à
    volta do `{{ }}` no ficheiro. Um título com aspas ou barra invertida
    partiria o corpo se fossem postas à mão; pôr as duas coisas parte-o já.

    Substituem-se as expressões por um literal e valida-se o resto.
    """
    bruto = _no(_fluxo("01-enviar-template.json"), "Meta: enviar template")["parameters"]["jsonBody"]
    # Primeiro as expressões que já vêm entre aspas no ficheiro (`"{{ … }}"`),
    # depois as que trazem as suas por `JSON.stringify`. Pela ordem inversa
    # sairia `""X""` e o corpo deixava de fazer sentido.
    literal = re.sub(r'"\{\{.*?\}\}"', '"X"', bruto.lstrip("="))
    corpo = json.loads(re.sub(r"\{\{.*?\}\}", '"X"', literal))

    assert corpo["type"] == "template"
    assert corpo["template"]["language"]["code"] == "pt_PT"
    parametros = corpo["template"]["components"][0]["parameters"]
    assert [p["type"] for p in parametros] == ["text", "text"]


def test_o_nome_do_template_e_o_mesmo_nos_dois_fluxos():
    """O `01` e o `02` mandam o MESMO template aprovado, por caminhos
    diferentes. Trocar o nome num e esquecer o outro faz o backfill enviar o
    template antigo — e o texto que fica em `leads.template_enviado` deixa de ser
    o que a pessoa recebeu."""
    bruto = _no(_fluxo("01-enviar-template.json"), "Meta: enviar template")["parameters"]["jsonBody"]
    literal = re.sub(r'"\{\{.*?\}\}"', '"X"', bruto.lstrip("="))
    do_01 = json.loads(re.sub(r"\{\{.*?\}\}", '"X"', literal))["template"]["name"]

    # No nó nativo o valor é `nome|idioma`.
    do_02 = _no(_fluxo("02-backfill-template.json"), "WhatsApp: enviar template")
    nome_02, _, idioma = do_02["parameters"]["template"].partition("|")

    assert do_01 == nome_02, f"01 manda '{do_01}', 02 manda '{nome_02}'"
    assert do_01 == _NOME_TEMPLATE, "não é o template aprovado na Meta"
    assert idioma == "pt_PT"


def test_o_no_da_meta_manda_dois_parametros_por_ordem():
    """`01` monta o JSON à mão; `02` usa o nó da Meta. Ambos, dois, por ordem."""
    bruto = _no(_fluxo("01-enviar-template.json"), "Meta: enviar template")["parameters"]["jsonBody"]
    assert bruto.index("nome_lead") < bruto.index("imovel_descrito")

    zap = _no(_fluxo("02-backfill-template.json"), "WhatsApp: enviar template")
    params = zap["parameters"]["components"]["component"][0]["bodyParameters"]["parameter"]
    assert len(params) == 2
    assert "nome_lead" in params[0]["text"]
    assert "imovel_descrito" in params[1]["text"]


@pytest.mark.parametrize("nome,ref,titulo", [
    ("Ana Reis", "FH2572", "T4 na cidade em excelente estado com garagem"),
    ("Abílio", "FH2450A", "T1+1 inteiramente renovado a 100m da praia de Buarcos na Figueira da Foz"),
    ("Ana Reis", "FH2572", None),                 # ref fora da `imoveis` (reservado, retirado)
    ("", "FH2572", "T4 na cidade"),               # lead sem nome
    ("Ana", None, None),                          # sem ref nenhuma
    ("  ", None, None),                           # o pior caso: nada de nada
])
def test_nenhum_parametro_sai_vazio_nem_com_quebras(nome, ref, titulo):
    p1, p2, corpo = _render(nome, ref, titulo)
    for etiqueta, valor in (("{{1}}", p1), ("{{2}}", p2)):
        assert valor, f"{etiqueta} vazio — a Cloud API recusa e o nó aborta"
        assert not _PROIBIDO_NO_PARAMETRO.search(valor), f"{etiqueta} tem quebra de linha ou tab"
    assert len(corpo) <= _LIMITE_CORPO


def test_a_degradacao_nao_parte_a_frase():
    assert _render("Ana", "FH2572", None)[1] == "FH2572"
    assert _render("Ana", None, "T4 na cidade")[1] == "T4 na cidade"
    assert _render("Ana", None, None)[1] == _FALLBACK_IMOVEL


def test_primeiro_nome_e_nao_o_nome_todo():
    """Igual ao fluxo 03. "Olá Ana Sofia Reis Marques," não é como se fala."""
    assert _render("Ana Sofia Reis Marques", "FH1", "x")[0] == "Ana"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
