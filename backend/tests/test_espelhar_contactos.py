"""`_espelhar_em_contactos` (guards.py, 2026-09-21) — espelho aditivo dos
assistentes em `contactos`, pedido do utilizador para corrigir "Leads
captados" idêntico em todos os assistentes (`agente_clientes` não tem
coluna a dizer quem captou o quê).

Regra que importa: nunca mexe numa linha que não seja dela própria — só
procura/actualiza onde `agente is not null` (dedup do `contactos` legado é
inseguro, dois escritores de fora: scraper + pipeline do Miguel).

Corre com `pytest backend/tests/` ou directamente com
`python backend/tests/test_espelhar_contactos.py`.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker.guards import _espelhar_em_contactos  # noqa: E402


class _FakeContactosSupabase:
    def __init__(self, existente=None):
        self.existente = existente
        self.inserted = None
        self.updated = None
        self.updated_eq = None
        self.chamadas = 0

    def table(self, nome):
        assert nome == "contactos"
        self.chamadas += 1
        return _FakeContactosQuery(self)


class _FakeContactosQuery:
    def __init__(self, parent):
        self._parent = parent
        self._modo = None

    @property
    def not_(self):
        return self

    def is_(self, *a, **kw):
        return self

    def select(self, *a, **kw):
        return self

    def in_(self, *a, **kw):
        return self

    def limit(self, *a, **kw):
        return self

    def eq(self, campo, valor):
        if self._modo == "update":
            self._parent.updated_eq = (campo, valor)
        return self

    def insert(self, row):
        self._modo = "insert"
        self._parent.inserted = row
        return self

    def update(self, row):
        self._modo = "update"
        self._parent.updated = row
        return self

    def execute(self):
        if self._modo == "insert":
            return SimpleNamespace(data=[{**self._parent.inserted, "id": "novo-id"}])
        if self._modo == "update":
            return SimpleNamespace(data=[self._parent.updated])
        existente = self._parent.existente
        return SimpleNamespace(data=[existente] if existente else [])


def test_sem_agente_nao_toca_na_base():
    supabase = _FakeContactosSupabase()
    _espelhar_em_contactos(
        supabase, nome="Ana", telefone="912345678", email=None,
        agente=None, tipo_interesse="compra",
    )
    assert supabase.chamadas == 0


def test_sem_telefone_nem_email_nao_toca_na_base():
    supabase = _FakeContactosSupabase()
    _espelhar_em_contactos(
        supabase, nome="Ana", telefone=None, email=None,
        agente="a1_vendedor", tipo_interesse="compra",
    )
    assert supabase.chamadas == 0


def test_contacto_novo_insere_com_tipo_contacto_mapeado():
    supabase = _FakeContactosSupabase(existente=None)
    _espelhar_em_contactos(
        supabase, nome="Ana Luísa", telefone="912345678", email=None,
        agente="a4_angariador", tipo_interesse="venda",
    )
    assert supabase.inserted["nome"] == "Ana Luísa"
    assert supabase.inserted["telefone"] == "912345678"
    assert supabase.inserted["agente"] == "a4_angariador"
    assert supabase.inserted["estado"] == "nova"
    assert supabase.inserted["tipo_contacto"] == ["vendedor"]
    assert supabase.updated is None


def test_contacto_existente_actualiza_em_vez_de_duplicar():
    """Segunda mensagem da mesma pessoa (mesmo telefone, já com `agente`
    preenchido de uma vez anterior) não pode criar uma segunda linha."""
    existente = {"id": "existente-1", "nome": "Ana Luísa", "tipo_contacto": ["comprador"]}
    supabase = _FakeContactosSupabase(existente=existente)
    _espelhar_em_contactos(
        supabase, nome="Ana Luísa", telefone="912345678", email=None,
        agente="a1_vendedor", tipo_interesse="arrendamento",
    )
    assert supabase.inserted is None
    assert supabase.updated_eq == ("id", "existente-1")
    assert supabase.updated["agente"] == "a1_vendedor"
    # "arrendamento" mapeia para "comprador" — já lá estava, junta sem duplicar.
    assert supabase.updated["tipo_contacto"] == ["comprador"]


def test_contacto_existente_acrescenta_novo_tipo_sem_perder_o_antigo():
    existente = {"id": "existente-2", "nome": "Ana Luísa", "tipo_contacto": ["comprador"]}
    supabase = _FakeContactosSupabase(existente=existente)
    _espelhar_em_contactos(
        supabase, nome="Ana Luísa", telefone="912345678", email=None,
        agente="a3_recrutamento", tipo_interesse="recrutamento",
    )
    assert sorted(supabase.updated["tipo_contacto"]) == ["comprador", "recrutamento"]


def test_contacto_existente_nao_sobrescreve_nome_ja_preenchido():
    existente = {"id": "existente-3", "nome": "Nome Antigo", "tipo_contacto": []}
    supabase = _FakeContactosSupabase(existente=existente)
    _espelhar_em_contactos(
        supabase, nome="Nome Novo Dito Agora", telefone="912345678", email=None,
        agente="a1_vendedor", tipo_interesse=None,
    )
    assert "nome" not in supabase.updated


def test_dedup_por_email_quando_sem_telefone():
    existente = {"id": "existente-4", "nome": "Sem Telefone", "tipo_contacto": []}
    supabase = _FakeContactosSupabase(existente=existente)
    _espelhar_em_contactos(
        supabase, nome="Sem Telefone", telefone=None, email="sem.telefone@exemplo.pt",
        agente="a3_recrutamento", tipo_interesse="recrutamento",
    )
    assert supabase.inserted is None
    assert supabase.updated_eq == ("id", "existente-4")


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
