"""O A1 às vezes escreve tipo/orçamento/zona em prosa no `resumo` e deixa os
campos estruturados a null -- e `guards.lead_qualificada` só olha aos campos,
nunca ao texto (achado ao vivo: Filipa Pedro e Junior Marques, 2026-08-31).
`_guardar_dados_cliente` tem de recuperar isso com uma extracção, não perder
a qualificação em silêncio."""

import asyncio

from app.agents.broker import tools


class _FakeBlock:
    def __init__(self, name, input_):
        self.type = "tool_use"
        self.name = name
        self.input = input_


class _FakeResp:
    def __init__(self, content):
        self.content = content


def _stub_extracao(monkeypatch, extraidos):
    async def _fake_create(**kwargs):
        return _FakeResp([_FakeBlock("extrair_mql", extraidos)])

    monkeypatch.setattr(tools._anthropic.messages, "create", _fake_create)


def test_preenche_campos_vazios_a_partir_do_resumo(monkeypatch):
    _stub_extracao(monkeypatch, {
        "tipo_interesse": "compra", "orcamento": 350000, "zona_preferida": "Figueira da Foz",
    })

    capturado = {}

    async def _fake_find_or_create(**kw):
        capturado.update(kw)
        return {"id": "cliente-1"}

    monkeypatch.setattr(tools, "find_or_create_cliente", _fake_find_or_create)
    async def _fake_run(fn, *a):
        return None

    monkeypatch.setattr(tools, "_run", _fake_run)

    inputs = {
        "nome": "Filipa Pedro",
        "resumo": "Procura moradia T3, máximo 350 mil, na Figueira da Foz.",
    }
    asyncio.run(tools._guardar_dados_cliente(inputs, {"telefone": "967209443"}))

    assert capturado["tipo_interesse"] == "compra"
    assert capturado["orcamento"] == 350000
    assert capturado["zona_preferida"] == "Figueira da Foz"


def test_nao_sobrepoe_o_que_o_modelo_ja_deu(monkeypatch):
    _stub_extracao(monkeypatch, {"tipo_interesse": "arrendamento", "zona_preferida": "Buarcos"})

    capturado = {}

    async def _fake_find_or_create(**kw):
        capturado.update(kw)
        return {"id": "cliente-2"}

    monkeypatch.setattr(tools, "find_or_create_cliente", _fake_find_or_create)
    async def _fake_run(fn, *a):
        return None

    monkeypatch.setattr(tools, "_run", _fake_run)

    inputs = {
        "nome": "Ana",
        "tipo_interesse": "compra",  # já veio preenchido -- a extracção não pode mudar isto
        "resumo": "Quer arrendar em Buarcos.",
    }
    asyncio.run(tools._guardar_dados_cliente(inputs, {}))

    assert capturado["tipo_interesse"] == "compra"
    assert capturado["zona_preferida"] == "Buarcos"


def test_nao_chama_extracao_quando_ja_esta_tudo_preenchido(monkeypatch):
    chamou = {"sim": False}

    async def _fake_create(**kwargs):
        chamou["sim"] = True
        return _FakeResp([])

    monkeypatch.setattr(tools._anthropic.messages, "create", _fake_create)

    async def _fake_find_or_create(**kw):
        return {"id": "cliente-3"}

    monkeypatch.setattr(tools, "find_or_create_cliente", _fake_find_or_create)
    async def _fake_run(fn, *a):
        return None

    monkeypatch.setattr(tools, "_run", _fake_run)

    inputs = {
        "nome": "Bruno",
        "tipo_interesse": "compra",
        "orcamento": 200000,
        "zona_preferida": "Quiaios",
        "resumo": "Já tudo combinado.",
    }
    asyncio.run(tools._guardar_dados_cliente(inputs, {}))

    assert chamou["sim"] is False
