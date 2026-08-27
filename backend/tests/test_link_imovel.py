"""`link_imovel` — o link da landing page do imóvel.

O que estes testes protegem, por ordem de gravidade:

1. **Todo o imóvel publicado tem link.** Houve aqui uma regra que só deixava
   passar `FH\\d+` e recusava as 16 referências com sufixo — a Matilde chegou a
   dizer a um cliente que o `FH2450A` não tinha página, e tem. O site lê a MESMA
   tabela `imoveis` com `imovel_ref=eq.<ref>`: se está publicado para nós, ele
   encontra-o (54/54, verificado a 2026-08-25). O que falta às 16 é só o
   **prerender** das OG tags, e isso é cosmético — o cartão do WhatsApp sai
   genérico, o link funciona.
2. **As referências com espaço vão codificadas.** 11 têm um espaço a sério
   (`FH2460 3C`); cru, o WhatsApp parte o endereço em duas palavras.
3. **`publicado=True` é fronteira**, a mesma do `ficha_imovel`.
4. **O URL usa a referência da base**, não a que o modelo escreveu.

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


@pytest.mark.parametrize("ref", ["FH2483_C", "FH2318A", "FH2450B", "FH2450A"])
def test_ref_com_sufixo_tem_link_na_mesma(pedir, ref):
    """A regressão que originou este ficheiro.

    Uma regra `FH\\d+` recusava estas referências, e a Matilde dizia ao cliente
    que o imóvel não tinha página. Tem: o `FH2450A` é um T1+1 em Buarcos a
    199 000 €, com 23 fotografias. Faltava-lhe o prerender das OG tags, não a
    página.
    """
    r = pedir(imovel_ref=ref)
    assert f"https://imoveis.figueirahome.pt/{ref}" in r
    assert "não tem" not in r


def test_ref_com_espaco_vai_codificada(pedir):
    """11 referências têm espaço a sério. Cru, o WhatsApp parte o link em duas."""
    r = pedir(imovel_ref="FH2460 3C")
    assert "https://imoveis.figueirahome.pt/FH2460%203C" in r
    assert "FH2460 3C\n" not in r, "espaço cru no endereço parte o link"


def test_imovel_desconhecido(pedir, monkeypatch):
    """Referência que não existe de todo — nem publicada, nem na tabela."""
    monkeypatch.setattr(tools, "_imovel_para_link", lambda ref: None)
    monkeypatch.setattr(tools, "_por_referencia", lambda campos, ref, apenas_publicados=True: None)
    assert "Não encontrei" in pedir()


# ── Existe, mas não está para vender ──────────────────────────
#
# O eGO tem um interruptor por imóvel — "publicar no site apesar de
# indisponível" — activado no FH2520 a 2026-08-27. Com ele o anúncio continua a
# correr sobre um imóvel reservado, e a lead chega à A1 a perguntar por ele.
# Antes disto ela dizia "o sistema não está a devolver a ficha" e escalava, ou
# adivinhava: medido ao vivo, **"pode ter sido vendido"** sobre um reservado.


@pytest.fixture
def indisponivel(monkeypatch):
    """A ref não está publicada, mas existe na tabela com esta disponibilidade."""
    def _montar(disponibilidade):
        monkeypatch.setattr(tools, "_imovel_para_link", lambda ref: None)
        monkeypatch.setattr(
            tools, "_por_referencia",
            lambda campos, ref, apenas_publicados=True: (
                None if apenas_publicados
                else {"imovel_ref": "FH2520", "disponibilidade": disponibilidade}
            ),
        )
        return asyncio.run(tools._link_imovel({"imovel_ref": "FH2520"}, CONTEXTO))
    return _montar


@pytest.mark.parametrize("estado,esperado", [
    ("Reservado", "RESERVADO"),
    ("Vendido", "já foi vendido"),
    ("Arrendado", "já foi arrendado"),
])
def test_diz_o_estado_real_em_vez_de_nao_encontrei(indisponivel, estado, esperado):
    r = indisponivel(estado)
    assert esperado in r
    assert "Não encontrei" not in r, "dizer que não encontrou é a mentira que isto corrige"
    assert "não inventes o motivo" in r


def test_estado_incerto_nao_ganha_motivo_inventado(indisponivel):
    """`Por validar` / `Retirado`: nem nós sabemos porquê. Não inventar."""
    r = indisponivel("Por validar")
    assert "não está disponível de momento" in r
    for palavra in ("vendido", "arrendado", "RESERVADO"):
        assert palavra not in r


def test_reservado_nao_promete_que_fica_livre(indisponivel):
    assert "Não prometas" in indisponivel("Reservado")


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
