"""A escalada completa a ficha do cliente (tipo, orçamento, zona) a partir do resumo, para a lead poder qualificar (FH2572, 21/11).

Sem rede: o extrator e `find_or_create_cliente` são duplos."""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.agents.broker.tools as tools  # noqa: E402

RESUMO = "Apresentou proposta de compra de 240000 euros para um T4 em Tavarede."


def _escalar(monkeypatch, agente, extraidos, motivo="reclamação"):
    gravados, chamadas = [], []

    async def _cliente(**kw):
        gravados.append(kw)

    async def _extrator(resumo):
        chamadas.append(resumo)
        return extraidos

    monkeypatch.setattr(tools, "find_or_create_cliente", _cliente)
    monkeypatch.setattr(tools, "_extrair_mql_do_resumo", _extrator)
    monkeypatch.setattr(tools, "_inserir_tarefa", lambda *a, **k: None)
    monkeypatch.setattr(tools, "notificar", lambda *a, **k: None)
    monkeypatch.setattr(tools, "_tarefa_ja_registada", lambda *a: False)
    ctx = {"canal": "whatsapp", "telefone": "912345678", "agente": agente, "conversa_id": "c-1"}
    asyncio.run(tools._escalar_para_humano({"motivo": motivo, "resumo": RESUMO, "nome": "Ana", "telefone": "912345678"}, ctx))
    return gravados, chamadas


def test_escalada_da_matilde_grava_tipo_orcamento_e_zona(monkeypatch):
    gravados, _ = _escalar(monkeypatch, "a1_vendedor", {"tipo_interesse": "compra", "orcamento": 240000, "zona_preferida": "Figueira da Foz"})
    assert gravados[0]["tipo_interesse"] == "compra" and gravados[0]["orcamento"] == 240000 and gravados[0]["zona_preferida"] == "Figueira da Foz"
    assert gravados[0]["notas"] == RESUMO


@pytest.mark.parametrize("agente", ["a3_recrutamento", "a4_angariador"])
def test_ines_e_barbara_nao_mexem_no_tipo_de_interesse(monkeypatch, agente):
    gravados, chamadas = _escalar(monkeypatch, agente, {"tipo_interesse": "compra", "orcamento": 1, "zona_preferida": "x"})
    assert chamadas == [] and "tipo_interesse" not in gravados[0]  # nem sequer chama o modelo


@pytest.mark.parametrize("tipo", ["venda", "recrutamento", "outro", None])
def test_so_compra_e_arrendamento_chegam_a_ficha(monkeypatch, tipo):
    gravados, _ = _escalar(monkeypatch, "a1_vendedor", {"tipo_interesse": tipo, "orcamento": 240000})
    assert "tipo_interesse" not in gravados[0] and "orcamento" not in gravados[0]


def test_extrator_vazio_nao_derruba_a_escalada(monkeypatch):
    gravados, _ = _escalar(monkeypatch, "a1_vendedor", {})
    assert len(gravados) == 1 and gravados[0]["notas"] == RESUMO and "tipo_interesse" not in gravados[0]
