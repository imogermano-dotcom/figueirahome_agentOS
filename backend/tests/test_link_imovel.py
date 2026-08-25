"""`link_imovel` — o link da landing page do imóvel.

O que estes testes protegem, por ordem de gravidade:

1. **O link só sai para referências que têm página.** Das 54 publicadas, 38 têm;
   as 16 que não têm são exactamente as de referência com sufixo. O site é uma
   SPA e devolve **HTTP 200** para tudo — uma referência sem página cai na
   homepage genérica e nada no protocolo denuncia o engano, portanto não há
   validação em runtime possível. Verificado ao vivo a 2026-08-25.
2. **`publicado=True` é fronteira**, a mesma do `ficha_imovel`.
3. **O URL usa a referência da base**, não a que o modelo escreveu.

Corre com `pytest backend/tests/` ou directamente com
`python backend/tests/test_link_imovel.py`.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.agents.broker.tools as tools  # noqa: E402

CONTEXTO = {"canal": "whatsapp", "telefone": "912345678", "agente": "a1_vendedor"}


@pytest.fixture
def pedir(monkeypatch):
    """`tools` sem DB. Devolve uma função que chama a tool."""
    estado = {"imovel": {"imovel_ref": "FH2571", "titulo": "T2 com terraço"}}
    monkeypatch.setattr(tools, "_imovel_para_link", lambda ref: estado["imovel"])

    def chamar(ref="FH2571", imovel_ref=None):
        if imovel_ref is not None:
            estado["imovel"] = {"imovel_ref": imovel_ref, "titulo": "x"}
        return asyncio.run(tools._link_imovel({"imovel_ref": ref}, CONTEXTO))

    return chamar


def test_devolve_o_link_da_landing_page(pedir):
    r = pedir()
    assert "https://imoveis.figueirahome.pt/FH2571" in r
    # "Escreve", não "enviei": o link só chega ao cliente se o modelo o escrever.
    assert "Escreve este endereço" in r


def test_usa_a_ref_da_base_e_nao_a_que_o_modelo_escreveu(pedir):
    assert "https://imoveis.figueirahome.pt/FH2571" in pedir(ref="fh 2571")


@pytest.mark.parametrize("ref", ["FH2460 3C", "FH2483_C", "FH2318A", "FH2450B"])
def test_ref_com_sufixo_nao_tem_landing_page(pedir, ref):
    """As 16 refs com sufixo caem na homepage genérica, com HTTP 200.

    A base (`FH2460`) tem página, mas é a do empreendimento inteiro e com outro
    preço — por isso não serve de alternativa e não sai link nenhum.
    """
    r = pedir(imovel_ref=ref)
    assert "imoveis.figueirahome.pt" not in r, f"{ref} não tem página própria"
    assert "não tem página própria" in r


def test_imovel_nao_publicado_nao_tem_link(pedir, monkeypatch):
    """Mesma fronteira do `ficha_imovel` — `_por_referencia` filtra `publicado`."""
    monkeypatch.setattr(tools, "_imovel_para_link", lambda ref: None)
    assert "Não encontrei" in pedir()


def test_sem_referencia_nao_inventa(pedir):
    assert "É preciso a referência" in asyncio.run(
        tools._link_imovel({}, CONTEXTO)
    )


def test_ref_com_espaco_e_procurada_como_veio_antes_de_comprimida():
    """As 11 fracções `FH2460 <x>` eram invisíveis às duas tools.

    O `replace(" ", "")` existia para o cliente que escreve `FH 2233`, e
    aplicava-se sempre: `FH2460 3C` virava `FH24603C`, que não existe, e o
    `ficha_imovel` respondia "não encontrei" a um imóvel publicado.
    """
    assert tools._refs_candidatas("FH2460 3C") == ["FH2460 3C", "FH24603C"]
    assert tools._refs_candidatas("FH 2233") == ["FH 2233", "FH2233"]
    assert tools._refs_candidatas("  FH2571 ") == ["FH2571"], "sem alternativa inútil"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
