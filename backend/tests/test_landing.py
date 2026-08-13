"""Landing pages — o que não pode partir sem se dar por isso.

Corre sem base de dados e sem API: renderiza os templates com dados fabricados.

    pytest backend/tests/test_landing.py      (a partir de `backend/`)
    python backend/tests/test_landing.py
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.landing import (  # noqa: E402
    PRAZOS,
    GateForm,
    _contexto_conteudo,
    _contexto_pagina,
    _templates,
)
from app.landing.gerador import (  # noqa: E402
    CAMPOS_PROIBIDOS,
    CAMPOS_PUBLICOS,
    fonte_hash,
    gerar_slug,
    slugify,
)

IMOVEL = {
    "imovel_ref": "FH2450",
    "natureza": "Moradia",
    "titulo": "Moradia T3 em Buarcos",
    "descricao": "Descrição vinda do CRM.",
    "quartos": 3,
    "casas_banho": 2,
    "area_util": 145,
    "venda_preco": 350000,
    "arrendamento_preco": None,
    "morada": "Rua das Acácias 12",
    "codigo_postal": "3080-100",
    "concelho": "Figueira da Foz",
    "freguesia": "Buarcos",
    "piscina": True,
    "garagem": True,
    "vista_mar": True,
    "foto_principal": "https://cdn.ego/1.jpg",
    "fotos": ["https://cdn.ego/1.jpg", "https://cdn.ego/2.jpg"],
    "plantas": [],
    "panoramic_url": None,
    "video_url": None,
    "publicado": True,
}

CONTEUDO = {
    "headline": "Moradia T3 a cinco minutos da praia de Buarcos",
    "subheadline": "145 m² úteis, piscina e garagem, na Figueira da Foz.",
    "destaques": ["Piscina privativa", "Garagem fechada", "Vista de mar", "145 m² úteis"],
    "descricao_longa": ["SEGREDO-PRIMEIRO-PARAGRAFO", "Segundo parágrafo."],
    "envolvente": "Buarcos fica no extremo norte da baía da Figueira da Foz.",
    "cta": "Receba as fotos e a morada",
}

LP = {
    "imovel_ref": "FH2450",
    "slug": "fh2450-moradia-t3-buarcos",
    "conteudo": CONTEUDO,
    "extras": {"video_url": "https://youtu.be/x", "notas": "NOTA-DO-CONSULTOR"},
    "mostrar_preco": True,
}


class _Url(str):
    """`str(request.url)` e `request.url.path` — é tudo o que o contexto usa."""

    @property
    def path(self):
        return str(self)


def _pedido(caminho="/lp/fh2450-moradia-t3-buarcos", cabecalhos=None):
    """Chega ao template o suficiente: os templates não usam `url_for`."""
    return SimpleNamespace(url=_Url(caminho), headers=cabecalhos or {})


def _render(nome, contexto):
    return _templates.env.get_template(nome).render(contexto)


def pagina(imovel=None, lp=None):
    return _render("imovel.html", _contexto_pagina(_pedido(), lp or LP, imovel or IMOVEL))


# ── Fronteira de segurança ────────────────────────────────────


def test_allowlist_nao_deixa_sair_dados_internos():
    """`imoveis` tem proprietário, angariador e comissões. A página é anónima.

    Este teste falha se alguém trocar a allowlist por `select("*")` ou lá meter
    uma coluna nova do eGO sem olhar para o que ela contém.
    """
    publicos = {c.strip() for c in CAMPOS_PUBLICOS.split(",")}
    fugas = publicos & set(CAMPOS_PROIBIDOS)
    assert not fugas, f"colunas internas na página pública: {fugas}"
    assert "*" not in CAMPOS_PUBLICOS
    assert all("comissao" not in c for c in publicos)


def test_gate_esconde_mesmo_o_conteudo():
    """O gate é do lado do servidor: o que está atrás dele não vem no HTML."""
    html = pagina()
    assert "SEGREDO-PRIMEIRO-PARAGRAFO" not in html      # descrição longa
    assert "Rua das Acácias" not in html                  # morada exacta
    assert "cdn.ego/2.jpg" not in html                    # galeria
    assert "NOTA-DO-CONSULTOR" not in html                # notas do consultor
    assert "youtu.be" not in html                         # vídeo
    # E o que faz decidir preencher o formulário tem de lá estar.
    assert CONTEUDO["headline"] in html
    assert "Piscina privativa" in html


def test_conteudo_gerado_e_escapado():
    """Conteúdo escrito por um modelo entra no HTML como texto, nunca como markup."""
    veneno = dict(CONTEUDO, headline='<script>alert(1)</script>')
    html = pagina(lp=dict(LP, conteudo=veneno))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ── Preço: chamariz vs. qualificador ──────────────────────────


def test_preco_visivel_apenas_quando_pedido():
    assert "350 000 €" in pagina()
    assert "350 000 €" not in pagina(lp=dict(LP, mostrar_preco=False))


def test_arrendamento_muda_rotulo_e_pergunta():
    arrendar = dict(IMOVEL, venda_preco=None, arrendamento_preco=900)
    html = pagina(imovel=arrendar)
    assert "Renda mensal" in html
    assert "Quando pretende arrendar?" in html
    assert "Quando pretende comprar?" in pagina()


# ── Imóvel fora do eGO ────────────────────────────────────────


def test_imovel_nao_publicado_avisa_e_continua_a_captar():
    """`publicado` (GENERATED, 0008) é a única fonte do estado — sem cron."""
    html = pagina(imovel=dict(IMOVEL, publicado=False))
    assert "já não está disponível" in html
    # O formulário fica: quem chega por um anúncio antigo ainda vale como lead.
    assert 'id="form-gate"' in html


# ── Gate ──────────────────────────────────────────────────────


def test_formulario_tem_os_quatro_campos_e_o_honeypot():
    html = pagina()
    for campo in ("nome", "telefone", "email", "prazo_compra"):
        assert f'name="{campo}"' in html, campo
    assert 'name="empresa"' in html, "honeypot em falta"
    assert len(PRAZOS) == 4
    for opcao in PRAZOS:
        assert opcao in html


# Payloads que passam o schema do pydantic (tamanhos) e só caem em `_validar` —
# é essa a camada que este teste cobre.
@pytest.mark.parametrize("payload", [
    {"nome": "Ana", "telefone": "912345678", "email": "sem-arroba", "prazo_compra": PRAZOS[0]},
    {"nome": "Ana", "telefone": "912345678", "email": "a@bcd", "prazo_compra": PRAZOS[0]},
    {"nome": "Ana", "telefone": "abcdef", "email": "a@b.pt", "prazo_compra": PRAZOS[0]},
    {"nome": "Ana", "telefone": "912345678", "email": "a@b.pt", "prazo_compra": "amanhã"},
])
def test_gate_rejeita_dados_invalidos(payload):
    from fastapi import HTTPException

    from app.api.landing import _validar

    with pytest.raises(HTTPException):
        _validar(GateForm(**payload))


def test_gate_aceita_dados_validos():
    from app.api.landing import _validar

    _validar(GateForm(
        nome="Ana Silva", telefone="+351 912 345 678",
        email="ana@exemplo.pt", prazo_compra=PRAZOS[0],
    ))


# ── Fragmento pós-gate ────────────────────────────────────────


def test_conteudo_pos_gate_traz_o_que_estava_escondido():
    html = _render("conteudo.html", _contexto_conteudo(_pedido(), LP, IMOVEL, "Ana Silva"))
    assert "SEGREDO-PRIMEIRO-PARAGRAFO" in html
    assert "Rua das Acácias" in html
    assert "cdn.ego/2.jpg" in html
    assert "NOTA-DO-CONSULTOR" in html
    assert "youtu.be" in html
    assert "Ana" in html and "Silva" not in html  # trata pelo primeiro nome
    assert "google.com/maps" in html               # mapa a partir da morada


def test_ficha_respeita_mostrar_preco():
    ctx = _contexto_conteudo(_pedido(), dict(LP, mostrar_preco=False), IMOVEL, "Ana")
    assert all("350 000" not in v for _, v in ctx["ficha"])


# ── Regeneração ───────────────────────────────────────────────


def test_hash_so_muda_quando_o_conteudo_mudaria():
    base = fonte_hash(IMOVEL, {}, True)
    assert base == fonte_hash(dict(IMOVEL), {}, True)
    assert base != fonte_hash(dict(IMOVEL, venda_preco=340000), {}, True)
    assert base != fonte_hash(IMOVEL, {"notas": "vista de mar"}, True)
    assert base != fonte_hash(IMOVEL, {}, False)
    # Campos que não vão ao prompt não podem obrigar a pagar API outra vez.
    assert base == fonte_hash(dict(IMOVEL, foto_principal="https://outra.jpg"), {}, True)
    assert base == fonte_hash(dict(IMOVEL, publicado=False), {}, True)


def test_formulario_aponta_para_o_caminho_publico_e_nao_para_o_interno():
    """Atrás do Worker da Cloudflare o backend vê `/lp/…`, o visitante vê `/imovel/…`.

    Sem isto, o POST do gate ia para um caminho que o domínio do site não serve
    e o formulário falhava só em produção.
    """
    pedido = _pedido("/lp/fh2450-moradia-t3-buarcos",
                     {"x-public-path": "/imovel/fh2450-moradia-t3-buarcos"})
    ctx = _contexto_pagina(pedido, LP, IMOVEL)
    assert ctx["acao_lead"] == "/imovel/fh2450-moradia-t3-buarcos/lead"

    # Com o domínio configurado (passo 3 da instalação do Worker), a `og:url` e
    # o canonical saem sob o domínio do site e com o caminho público.
    from app.config import settings
    original = settings.landing_base_url
    settings.landing_base_url = "https://figueirahome.pt"
    try:
        ctx = _contexto_pagina(pedido, LP, IMOVEL)
        assert ctx["page_url"] == "https://figueirahome.pt/imovel/fh2450-moradia-t3-buarcos"
    finally:
        settings.landing_base_url = original

    # Sem Worker (dev ou URL do Fly.io directo) o caminho do pedido já serve.
    assert _contexto_pagina(_pedido(), LP, IMOVEL)["acao_lead"] == \
        "/lp/fh2450-moradia-t3-buarcos/lead"


def test_slug_e_url_safe():
    assert gerar_slug(IMOVEL) == "fh2450-moradia-t3-buarcos"
    assert slugify("Praia da Figueira — Nº 3") == "praia-da-figueira-no-3"
    for texto in ("Ção/Ão", "a  b", "--x--"):
        s = slugify(texto)
        assert s == s.lower() and " " not in s and "--" not in s
        assert not s.startswith("-") and not s.endswith("-")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
