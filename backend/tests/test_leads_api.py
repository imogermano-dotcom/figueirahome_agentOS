"""`leads` como tabela única — o que a troca de `agente_leads` tinha de resolver.

O painel apontava para `agente_leads` (2 linhas de teste) enquanto 119 leads
pagas da Meta viviam em `leads`, invisíveis. E as duas origens guardam o contacto
em sítios diferentes: a Meta traz nome e telefone no formulário e nunca chega a
ter `cliente_id`; uma lead nascida numa conversa é ao contrário. Uma página que
só saiba de um dos casos mostra metade das leads sem nome.

    pytest backend/tests/test_leads_api.py      (a partir de `backend/`)
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.agents.broker.tools as tools  # noqa: E402
import app.agents.voice.save_call as save_call  # noqa: E402
from app.api import leads as api_leads  # noqa: E402
from app.models.lead import ESTADOS, ESTADOS_FECHADOS, ORIGENS  # noqa: E402


# ── contacto: da linha ou do cliente ligado ─────────────────────────────────

def test_lead_da_meta_mostra_o_contacto_da_propria_linha():
    """Sem `cliente_id`, e é a maioria: 119 leads da Meta."""
    lead = api_leads._com_contacto({
        "nome": "Isabel Braga", "telefone": "912345678",
        "cliente_id": None, "agente_clientes": None,
    })
    assert lead["nome_display"] == "Isabel Braga"
    assert lead["telefone_display"] == "912345678"


def test_lead_do_assistente_cai_no_cliente_ligado():
    """Nascida numa conversa: o contacto vive em `agente_clientes`."""
    lead = api_leads._com_contacto({
        "nome": None, "telefone": None,
        "agente_clientes": {"nome": "João Dias", "telefone": "913333444"},
    })
    assert lead["nome_display"] == "João Dias"
    assert lead["telefone_display"] == "913333444"


def test_a_linha_ganha_ao_cliente():
    """Havendo os dois, vale o que a lead trouxe — é o dado da origem, e o
    cliente pode estar ligado a outra pessoa da mesma casa."""
    lead = api_leads._com_contacto({
        "nome": "Isabel", "telefone": "912345678",
        "agente_clientes": {"nome": "Outro", "telefone": "999999999"},
    })
    assert lead["nome_display"] == "Isabel"
    assert lead["telefone_display"] == "912345678"


def test_sem_contacto_nenhum_nao_rebenta():
    lead = api_leads._com_contacto({"agente_clientes": None})
    assert lead["nome_display"] is None and lead["telefone_display"] is None


# ── os dois escritores marcam a origem ──────────────────────────────────────

class _Q:
    def __init__(self, tabela, estado):
        self.tabela, self.estado = tabela, estado
        self._abertas = estado["abertas"]

    def select(self, *a, **k):
        return self

    def insert(self, dados):
        self.estado["inserts"].append((self.tabela, dados))
        return self

    def eq(self, *a, **k):
        return self

    # No PostgREST `not_` é propriedade, não método: `q.not_.in_(...)`.
    @property
    def not_(self):
        return self

    def in_(self, campo, valores):
        self.estado["excluidos"] = list(valores)
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        return SimpleNamespace(data=self._abertas)


def _fake(monkeypatch, alvo, abertas=None):
    estado = {"inserts": [], "excluidos": None, "abertas": abertas or []}
    monkeypatch.setattr(alvo, "get_supabase", lambda: SimpleNamespace(
        table=lambda nome: _Q(nome, estado)), raising=False)
    return estado


def test_assistente_escreve_em_leads_com_origem(monkeypatch):
    estado = _fake(monkeypatch, tools)
    tools._criar_lead_se_preciso("cli-1", "quer T2 em Buarcos")

    assert estado["inserts"] == [("leads", {
        "cliente_id": "cli-1", "estado": "nova",
        "origem": "assistente", "notas": "quer T2 em Buarcos",
    })]


def test_assistente_nao_reabre_lead_ja_aberta(monkeypatch):
    estado = _fake(monkeypatch, tools, abertas=[{"id": "lead-1"}])
    tools._criar_lead_se_preciso("cli-1", "resumo")
    assert estado["inserts"] == []


def test_dedup_do_assistente_usa_o_vocabulario_novo(monkeypatch):
    """Com `fechado`/`perdido` (masculino, de `agente_leads`) o filtro deixava
    de excluir seja o que for e criava uma lead por conversa."""
    estado = _fake(monkeypatch, tools)
    tools._criar_lead_se_preciso("cli-1", "resumo")
    assert estado["excluidos"] == list(ESTADOS_FECHADOS)
    assert all(e in ESTADOS for e in estado["excluidos"])


def test_voz_escreve_em_leads_com_origem(monkeypatch):
    estado = {"inserts": [], "excluidos": None, "abertas": []}
    sb = SimpleNamespace(table=lambda nome: _Q(nome, estado))
    save_call._supabase_insert_lead(sb, "cli-2", {"resumo": "pediu T3"})

    assert estado["inserts"] == [("leads", {
        "cliente_id": "cli-2", "estado": "nova", "origem": "voz", "notas": "pediu T3",
    })]


def test_voz_sem_cliente_nao_escreve():
    estado = {"inserts": [], "excluidos": None, "abertas": []}
    sb = SimpleNamespace(table=lambda nome: _Q(nome, estado))
    save_call._supabase_insert_lead(sb, "", {"resumo": "x"})
    assert estado["inserts"] == []


# ── vocabulários ────────────────────────────────────────────────────────────

def test_estados_abertos_do_guards_existem_no_vocabulario():
    """`guards._ESTADOS_LEAD_ABERTA` decide que leads o A1 apanha. Um estado
    renomeado só aqui deixava-o a olhar para um conjunto vazio, em silêncio."""
    from app.agents.broker.guards import _ESTADOS_LEAD_ABERTA

    for estado in _ESTADOS_LEAD_ABERTA:
        assert estado in ESTADOS, f"{estado} saiu do vocabulário"
    assert not set(_ESTADOS_LEAD_ABERTA) & set(ESTADOS_FECHADOS)


def test_origens_cobrem_os_escritores():
    for origem in ("meta", "assistente", "voz", "landing", "manual"):
        assert origem in ORIGENS


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
