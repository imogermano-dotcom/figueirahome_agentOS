"""Pedido #20: rede em código quando o modelo não escala uma mensagem que precisa de uma pessoa
(`docs/fases/escalar-aviso-imediato-plano.md`). Sem rede: `execute_tool` é um duplo."""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker import engine  # noqa: E402
from app.agents.broker.guards import precisa_de_pessoa  # noqa: E402


@pytest.mark.parametrize("texto,motivo", [
    ("Olá, Amanhã pelas 18:30 poderá visitar o apartamento da Rua do Matadouro.", "mensagem para a equipa"),
    ("Confirmo a visita de amanhã às 18:30", "mensagem para a equipa"),
    ("Não vou poder estar na visita de sexta, podemos desmarcar?", "mensagem para a equipa"),
    ("Pode ser às 19:00 em vez das 18:30 na visita?", "mensagem para a equipa"),
    ("Bom dia, a visita de hoje às 15h mantém-se?", "mensagem para a equipa"),
    ("Sou o proprietário do apartamento da Rua X, queria saber como vai a venda", "mensagem para a equipa"),
    ("Passe-me por favor à consultora Sandra, preciso de falar com ela", "mensagem para a equipa"),
    ("Gostava de falar com uma pessoa, não com um robô", "mensagem para a equipa"),
    ("Quero fazer uma proposta de 250 mil euros pelo FH2572", "proposta de compra"),
    ("Estou muito desiludido, ninguém me responde há uma semana", "reclamação"),
    ("Quero apresentar uma reclamação", "reclamação"),
])
def test_deteta_o_que_precisa_de_uma_pessoa(texto, motivo):
    assert precisa_de_pessoa(texto) == motivo


@pytest.mark.parametrize("texto", [
    "Quero saber mais sobre o T3 em Buarcos", "Olá, bom dia", "Que imóveis têm para comprar na Figueira da Foz até 200 mil?",
    "Queria visitar o FH2572 no sábado de manhã", "Qual o preço?", "Obrigado, até breve", "Tenho um orçamento de 250 mil", "", None,
])
def test_nao_dispara_em_conversa_normal(texto):
    assert precisa_de_pessoa(texto) is None


CTX = {"canal": "whatsapp", "telefone": "912345678", "agente": "a1_vendedor", "conversa_id": "c-1"}


@pytest.fixture
def chamadas(monkeypatch):
    registo = []

    async def _tool(nome, inputs, contexto):
        registo.append((nome, inputs))
        return "ok"

    monkeypatch.setattr(engine, "execute_tool", _tool)
    return registo


def _rede(msg, agente="a1_vendedor", canal="whatsapp", usadas=()):
    return asyncio.run(engine._escalar_se_precisa(msg, agente, canal, list(usadas), CTX))


def test_modelo_nao_registou_nada_o_motor_escala_com_a_mensagem_tal_e_qual(chamadas):
    msg = "Gostava de falar com uma pessoa, não com um robô"
    assert _rede(msg) is True
    (nome, inputs), = chamadas
    assert nome == "escalar_para_humano" and inputs["resumo"] == msg and inputs["telefone"] == "912345678"
    assert inputs["motivo"] == "mensagem para a equipa"


@pytest.mark.parametrize("usadas", [("escalar_para_humano",), ("pedir_visita",), ("encerrar_lead",)])
def test_se_o_modelo_ja_registou_nao_duplica(chamadas, usadas):
    assert _rede("Confirmo a visita de amanhã às 18:30", usadas=usadas) is False and not chamadas


def test_so_whatsapp_matilde_e_maria(chamadas):
    assert _rede("Confirmo a visita de amanhã às 18:30", canal="site") is False
    assert _rede("Confirmo a visita de amanhã às 18:30", agente="a3_recrutamento") is False
    assert _rede("Confirmo a visita de amanhã às 18:30", agente="a4_angariador") is False
    assert _rede("Confirmo a visita de amanhã às 18:30", agente="a2_geral") is True


def test_conversa_normal_nao_escala_e_falha_da_tool_nao_levanta(chamadas, monkeypatch):
    assert _rede("Quero saber mais sobre o T3 em Buarcos") is False and not chamadas

    async def _rebenta(*a):
        raise RuntimeError("bd em baixo")

    monkeypatch.setattr(engine, "execute_tool", _rebenta)
    assert _rede("Estou muito desiludido, ninguém me responde") is False
