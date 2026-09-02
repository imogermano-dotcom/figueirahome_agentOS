"""Achado em produção a 2026-09-02: uma conversa do chat do site criou uma
lead sem forma nenhuma de contactar a pessoa. Causa: `find_or_create_cliente`
tratava `nome` sozinho como identificador suficiente para criar um cliente
(e, a seguir, uma lead) -- ao contrário do que o próprio docstring sempre
disse. No WhatsApp nunca se via, porque `contexto.get("telefone")` preenche
sempre; no site, sem telefone nem email, não pode nascer nada."""

import asyncio

import app.agents.broker.guards as guards


class _FakeQuery:
    def __init__(self):
        self.data = []

    def select(self, *a, **kw):
        return self

    def in_(self, *a, **kw):
        return self

    def eq(self, *a, **kw):
        return self

    def ilike(self, *a, **kw):
        return self

    def limit(self, *a, **kw):
        return self

    def insert(self, row):
        self.data = [{**row, "id": "novo-id"}]
        return self

    def update(self, row):
        self.data = [row]
        return self

    def execute(self):
        return self


class _FakeSupabase:
    def table(self, _nome):
        return _FakeQuery()


def test_nome_sozinho_nao_toca_a_base(monkeypatch):
    chamadas = []
    monkeypatch.setattr(guards, "get_supabase", lambda: chamadas.append(1))

    resultado = asyncio.run(guards.find_or_create_cliente(nome="Visitante Anónimo"))

    assert resultado is None
    assert chamadas == []  # nunca chegou a ir à BD


def test_nome_e_tipo_interesse_sem_contacto_tambem_nao_cria(monkeypatch):
    """O caso real: o modelo já sabe o que a pessoa quer, só não tem como a
    contactar. Continua a não dever nascer nada."""
    chamadas = []
    monkeypatch.setattr(guards, "get_supabase", lambda: chamadas.append(1))

    resultado = asyncio.run(
        guards.find_or_create_cliente(nome="Visitante", tipo_interesse="compra")
    )

    assert resultado is None
    assert chamadas == []


def test_com_telefone_cria_normalmente(monkeypatch):
    """Regressão: a correcção não pode impedir o caminho normal, com contacto real."""
    monkeypatch.setattr(guards, "get_supabase", lambda: _FakeSupabase())

    resultado = asyncio.run(
        guards.find_or_create_cliente(nome="Ana Luísa", telefone="912345678")
    )

    assert resultado is not None
    assert resultado["telefone"] == "912345678"


def test_so_email_tambem_cria(monkeypatch):
    monkeypatch.setattr(guards, "get_supabase", lambda: _FakeSupabase())

    resultado = asyncio.run(
        guards.find_or_create_cliente(nome="Ana Luísa", email="ana@exemplo.pt")
    )

    assert resultado is not None
    assert resultado["email"] == "ana@exemplo.pt"


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
