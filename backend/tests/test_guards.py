"""Guardas de negócio — funções puras, sem DB nem rede.

Corre com `pytest backend/tests/` ou directamente com
`python backend/tests/test_guards.py`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker.guards import (  # noqa: E402
    _compativel,
    _ESTADOS_LEAD_ABERTA,
    normalizar_email,
    normalizar_telefone,
    visita_permitida,
)
from app.models.lead import ESTADOS, ESTADOS_FECHADOS  # noqa: E402


def test_normalizar_telefone():
    # Mesmo número, quatro formatos vistos em produção (Meta, cliente, painel).
    assert normalizar_telefone("+351 912 345-678") == "912345678"
    assert normalizar_telefone("00351912345678") == "912345678"
    assert normalizar_telefone("351912345678") == "912345678"
    assert normalizar_telefone("912345678") == "912345678"
    assert normalizar_telefone("") is None
    assert normalizar_telefone(None) is None


def test_normalizar_email():
    assert normalizar_email("  A@B.COM ") == "a@b.com"
    assert normalizar_email("") is None
    assert normalizar_email(None) is None


def test_visita_permitida():
    # Spec §3.2: €240k sobre €300k é o limiar exacto e avança.
    assert visita_permitida(240000, 300000) is True
    assert visita_permitida(300000, 300000) is True
    assert visita_permitida(239999, 300000) is False
    assert visita_permitida(200000, 300000) is False


def test_visita_permitida_sem_dados():
    assert visita_permitida(None, 300000) is False  # spec 3c: insistir, não marcar
    assert visita_permitida(100000, None) is False  # sem preço, sem divisão por zero
    assert visita_permitida(100000, 0) is False


def test_compativel_preenche_dados_em_falta():
    """O bug de 2026-08-03: nome gravado sem telefone, telefone chega depois.

    `guardar_dados_cliente` grava o nome (o modelo nem sempre passa o
    telefone); no turno seguinte `agendar_visita` traz o telefone. Sem isto,
    a procura por telefone falhava e criava-se uma segunda linha.
    """
    existente = {"nome": "Carlos Mendes", "telefone": None, "email": None}
    assert _compativel(existente, "912777888", None) is True
    assert _compativel(existente, None, "c@x.pt") is True


def test_compativel_recusa_quando_ha_contradicao():
    """Dois homónimos com telefones diferentes são duas pessoas."""
    joao_a = {"nome": "João Silva", "telefone": "911111111", "email": None}
    assert _compativel(joao_a, "922222222", None) is False
    assert _compativel(joao_a, "911111111", None) is True
    # Formatos diferentes do MESMO número continuam compatíveis.
    assert _compativel({"nome": "X", "telefone": "351911111111"}, "911111111", None) is True

    com_email = {"nome": "Ana", "telefone": None, "email": "ana@x.pt"}
    assert _compativel(com_email, None, "outra@x.pt") is False
    assert _compativel(com_email, None, "ana@x.pt") is True


def test_compativel_sem_identificadores():
    """Nada a contradizer — o nome é o único dado que temos."""
    assert _compativel({"nome": "Ana", "telefone": None, "email": None}, None, None) is True


def test_engano_fecha_a_lead():
    """`engano` tem de estar fechado: é o que faz `lead_aberta` devolver None (o
    router larga a A1) e impede `_criar_lead_se_preciso` de a reabrir."""
    assert "engano" in ESTADOS
    assert "engano" in ESTADOS_FECHADOS
    assert "engano" not in _ESTADOS_LEAD_ABERTA


def test_sem_resposta_continua_aberta():
    """A regressão que interessa. `sem_resposta` quer dizer "desistimos de
    insistir", não "não falar com esta pessoa": quem responde uma semana depois
    do follow-up tem de manter a A1 e o `imovel_ref` do anúncio. Fechá-lo mandava
    essa pessoa para o A2 sem contexto nenhum — e é o erro fácil de cometer,
    porque o nome soa a desfecho final."""
    assert "sem_resposta" in ESTADOS
    assert "sem_resposta" in _ESTADOS_LEAD_ABERTA
    assert "sem_resposta" not in ESTADOS_FECHADOS


def test_vocabulario_do_painel_cobre_o_das_guardas():
    """`_ESTADOS_LEAD_ABERTA` e `ESTADOS_FECHADOS` são subconjuntos de `ESTADOS`,
    e não se sobrepõem. Um estado só num dos lados é uma lead invisível no painel
    ou um filtro que nunca bate."""
    assert set(_ESTADOS_LEAD_ABERTA) <= set(ESTADOS)
    assert set(ESTADOS_FECHADOS) <= set(ESTADOS)
    assert not set(_ESTADOS_LEAD_ABERTA) & set(ESTADOS_FECHADOS)


# ── recrutamento sem semeadura ──────────────────────────────────────────────
# `contacto_recrutamento_aberto`/`marcar_contacto_respondeu`/`agente_de_lead`
# não têm fixture de monkeypatch (ficheiro corre também sem pytest, ver
# `__main__` no fim) — patch manual com try/finally.

import asyncio  # noqa: E402

import app.agents.broker.guards as guards  # noqa: E402


def test_agente_de_lead_cai_para_recrutamento_sem_lead():
    """Sem lead aberta em `leads`, tenta `contactos` antes de desistir — é o
    fallback que substitui a semeadura para a Inês (sem ele, "Sim" ao 1º
    template cai na Maria/A2, mesmo bug que a semeadura evitava para o A1."""
    original_lead, original_contacto = guards.lead_aberta, guards.contacto_recrutamento_aberto

    async def _sem_lead(_tel):
        return None

    async def _candidato(_tel):
        return {"id": "contacto-1"}

    try:
        guards.lead_aberta = _sem_lead
        guards.contacto_recrutamento_aberto = _candidato
        assert asyncio.run(guards.agente_de_lead("912345678")) == "a3_recrutamento"

        guards.contacto_recrutamento_aberto = _sem_lead
        assert asyncio.run(guards.agente_de_lead("912345678")) is None
    finally:
        guards.lead_aberta = original_lead
        guards.contacto_recrutamento_aberto = original_contacto


def test_agente_de_lead_leads_ganha_a_contactos():
    """Uma lead aberta em `leads` (A1/A4) não é sequer substituída por olhar a
    `contactos` — o fallback só corre quando `leads` não tem nada."""
    original_lead, original_contacto = guards.lead_aberta, guards.contacto_recrutamento_aberto

    async def _lead(_tel):
        return {"tipo": "compra"}

    chamado = []

    async def _nao_devia_correr(_tel):
        chamado.append(True)
        return {"id": "x"}

    try:
        guards.lead_aberta = _lead
        guards.contacto_recrutamento_aberto = _nao_devia_correr
        assert asyncio.run(guards.agente_de_lead("912345678")) == "a1_vendedor"
        assert not chamado
    finally:
        guards.lead_aberta = original_lead
        guards.contacto_recrutamento_aberto = original_contacto


def test_marcar_contacto_respondeu_so_escreve_na_primeira_vez():
    """Espelha `marcar_lead_respondeu` — o filtro `is null` guarda o PRIMEIRO
    turno e é o que o fluxo de follow-up lê para saber que já não deve escrever."""
    chamadas = {}

    class _Q:
        def update(self, dados):
            chamadas["dados"] = dados
            return self

        def eq(self, campo, valor):
            chamadas[campo] = valor
            return self

        def is_(self, campo, valor):
            chamadas["filtro_is"] = (campo, valor)
            return self

        def execute(self):
            return None

    original = guards.get_supabase
    try:
        guards.get_supabase = lambda: type("S", (), {"table": lambda s, n: _Q()})()
        asyncio.run(guards.marcar_contacto_respondeu("contacto-1"))
    finally:
        guards.get_supabase = original

    assert chamadas["id"] == "contacto-1"
    assert chamadas["filtro_is"] == ("respondeu_em", "null")
    assert chamadas["dados"]["respondeu_em"]


def test_contacto_recrutamento_aberto_filtra_por_tipo_e_template():
    """A query real: `tipo_contacto` tem de conter `recrutamento` e
    `template_enviado_em` tem de estar preenchido — sem isto um candidato que
    nunca recebeu template seria tratado como se já estivesse em conversa."""
    chamadas = {}

    class _Not:
        def is_(self, campo, valor):
            chamadas["not_is"] = (campo, valor)
            return _Q_INSTANCE

    class _Q:
        def select(self, *a, **k):
            return self

        def in_(self, campo, valores):
            chamadas["in_"] = (campo, valores)
            return self

        def contains(self, campo, valor):
            chamadas["contains"] = (campo, valor)
            return self

        @property
        def not_(self):
            return _Not()

        def gte(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def execute(self):
            from types import SimpleNamespace
            return SimpleNamespace(data=[{"id": "contacto-9"}])

    _Q_INSTANCE = _Q()
    original = guards.get_supabase
    try:
        guards.get_supabase = lambda: type("S", (), {"table": lambda s, n: _Q_INSTANCE})()
        resultado = asyncio.run(guards.contacto_recrutamento_aberto("912345678"))
    finally:
        guards.get_supabase = original

    assert resultado == {"id": "contacto-9"}
    assert chamadas["contains"] == ("tipo_contacto", ["recrutamento"])
    assert chamadas["not_is"] == ("template_enviado_em", "null")


if __name__ == "__main__":
    for nome, fn in list(globals().items()):
        if nome.startswith("test_"):
            fn()
            print(f"  ok  {nome}")
    print("test_guards OK")
