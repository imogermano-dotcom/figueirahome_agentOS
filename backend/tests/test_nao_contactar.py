"""Recusa gravada em `contactos.nao_contactar_em` (pedido #49, migration 0053).

Caso real de 24/10: a Bárbara recebeu um nudge duas horas depois de a pessoa dizer «não estou interessada». O `encerrar_lead`
só escrevia em `leads` e os contactos de angariação e recrutamento vivem só em `contactos`. Sem rede.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker import engine, guards  # noqa: E402


@pytest.mark.parametrize("texto", ["Não me contactem mais", "nao me contactem", "Deixem de me enviar mensagens", "STOP",
                                    "parem de me ligar", "Não quero ser contactada", "Retirem-me da lista", "Não me ligue"])
def test_pedidos_explicitos_de_opt_out(texto):
    assert guards.e_optout_explicito(texto)


@pytest.mark.parametrize("texto", ["Não tenho interesse em arrendar, só comprar", "Não estou interessada, obrigada", "Quero comprar",
                                    "Não sei", "", None, "Obrigado"])
def test_conversa_normal_nao_e_opt_out(texto):
    assert not guards.e_optout_explicito(texto)


class _BD:
    """Duplo de `contactos` e `leads`: regista os updates e devolve linhas só onde as houver."""

    def __init__(self, contactos=1, leads=0, rebenta_contactos=False):
        self.n = {"contactos": contactos, "leads": leads}
        self.updates, self.rebenta, self._t = [], rebenta_contactos, None

    def table(self, nome):
        self._t = nome
        return self

    def __getattr__(self, nome):
        if nome == "not_":
            return self
        return lambda *a, **k: self

    def update(self, valores):
        self.updates.append((self._t, valores))
        return self

    def execute(self):
        if self.rebenta and self._t == "contactos":
            raise RuntimeError("BD em baixo")
        return type("R", (), {"data": [{}] * self.n[self._t]})()


def test_marcar_grava_nao_contactar_em(monkeypatch):
    bd = _BD(contactos=1)
    monkeypatch.setattr(guards, "get_supabase", lambda: bd)
    assert guards.marcar_nao_contactar("351912345678") == 1
    (tabela, valores), = bd.updates
    assert tabela == "contactos" and list(valores) == ["nao_contactar_em"] and valores["nao_contactar_em"]


def test_marcar_sem_telefone_nao_toca_na_bd(monkeypatch):
    monkeypatch.setattr(guards, "get_supabase", lambda: pytest.fail("não devia tocar na BD"))
    assert guards.marcar_nao_contactar(None) == 0


def test_marcar_nunca_levanta(monkeypatch):
    monkeypatch.setattr(guards, "get_supabase", lambda: _BD(rebenta_contactos=True))
    assert guards.marcar_nao_contactar("912345678") == 0


@pytest.mark.parametrize("motivo", ["engano", "sem_interesse", "pausa"])
def test_encerrar_lead_grava_a_recusa_mesmo_sem_linha_em_leads(monkeypatch, motivo):
    """O buraco do #49: angariação e recrutamento não têm linha em `leads`, e o `encerrar_lead` não deixava rasto."""
    bd = _BD(contactos=1, leads=0)
    monkeypatch.setattr(guards, "get_supabase", lambda: bd)
    ok = asyncio.run(guards.encerrar_lead_do_telefone("912345678", motivo, "não quer"))
    assert ok is True, "marcou o contacto, mesmo sem fechar nenhuma lead"
    assert ("contactos", bd.updates[0][1]) == bd.updates[0] and "nao_contactar_em" in bd.updates[0][1]


def test_encerrar_lead_continua_a_fechar_a_lead_quando_ela_existe(monkeypatch):
    bd = _BD(contactos=1, leads=1)
    monkeypatch.setattr(guards, "get_supabase", lambda: bd)
    assert asyncio.run(guards.encerrar_lead_do_telefone("912345678", "sem_interesse")) is True
    assert [t for t, _ in bd.updates] == ["contactos", "leads"] and bd.updates[1][1]["estado"] == "sem_interesse"


def test_motivo_invalido_nao_marca_nada(monkeypatch):
    monkeypatch.setattr(guards, "get_supabase", lambda: pytest.fail("não devia tocar na BD"))
    assert asyncio.run(guards.encerrar_lead_do_telefone("912345678", "outro")) is False


def test_falha_nos_contactos_nao_impede_de_fechar_a_lead(monkeypatch):
    bd = _BD(contactos=1, leads=1, rebenta_contactos=True)
    monkeypatch.setattr(guards, "get_supabase", lambda: bd)
    assert asyncio.run(guards.encerrar_lead_do_telefone("912345678", "engano")) is True


def _motor(monkeypatch, marcas):
    async def _carregar(canal, participante):
        return "c1", [], "a1_vendedor"

    async def _para(*a, **k):
        raise AssertionError("parou depois da marca (o modelo não é chamado no teste)")

    monkeypatch.setattr(engine, "load_conversation", _carregar)
    monkeypatch.setattr(engine, "load_config", _para)
    monkeypatch.setattr(engine, "marcar_nao_contactar", lambda tel: marcas.append(tel) or 1)


def test_motor_marca_o_opt_out_explicito_antes_de_chamar_o_modelo(monkeypatch):
    marcas = []
    _motor(monkeypatch, marcas)
    with pytest.raises(AssertionError):
        asyncio.run(engine._responder_sem_lock("whatsapp", "351912345678", "Não me contactem mais"))
    assert marcas == ["351912345678"]


def test_motor_nao_marca_uma_recusa_normal_nem_outros_canais(monkeypatch):
    marcas = []
    _motor(monkeypatch, marcas)
    with pytest.raises(AssertionError):
        asyncio.run(engine._responder_sem_lock("whatsapp", "351912345678", "Não estou interessada, obrigada"))
    with pytest.raises(AssertionError):
        asyncio.run(engine._responder_sem_lock("site", "visitante", "Não me contactem mais"))
    assert marcas == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
