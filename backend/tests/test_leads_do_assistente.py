"""Leads criadas pelos assistentes (`docs/fases/leads-do-assistente-plano.md`, 08/10).

Medido a 07/10: das 25 leads de assistentes, nenhuma foi qualificada, nenhuma tinha
telefone na linha (invisíveis a `lead_aberta`/router/nudge) e das 15 `compra` só 1 era
compra. Aqui um Supabase falso COM estado, para provar o comportamento de ponta a ponta.
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.agents.broker import guards, tools


class _Q:
    def __init__(self, db, nome):
        self.db, self.nome = db, nome
        self.filtros, self._op, self._dados, self._lim, self._neg = [], None, None, None, False

    @property
    def not_(self):
        self._neg = True
        return self

    def select(self, *a, **k):
        self._op = "select"
        return self

    def insert(self, dados):
        self._op, self._dados = "insert", dados
        return self

    def update(self, dados):
        self._op, self._dados = "update", dados
        return self

    def in_(self, coluna, valores):
        self.filtros.append((coluna, "in", list(valores), self._neg))
        self._neg = False
        return self

    def eq(self, coluna, valor):
        self.filtros.append((coluna, "eq", valor, False))
        return self

    def gte(self, coluna, valor):
        self.filtros.append((coluna, "gte", valor, False))
        return self

    def limit(self, n):
        self._lim = n
        return self

    def _passa(self, linha):
        for coluna, op, valor, negado in self.filtros:
            x = linha.get(coluna)
            if op == "in":
                ok = x in valor
            elif op == "eq":
                ok = x == valor
            else:
                ok = x is not None and x >= valor
            if ok == negado:
                return False
        return True

    def execute(self):
        linhas = self.db.setdefault(self.nome, [])
        if self._op == "insert":
            nova = {"id": f"{self.nome}-{len(linhas) + 1}", "criado_em": "2099-01-01T00:00:00+00:00", **self._dados}
            linhas.append(nova)
            return SimpleNamespace(data=[nova])
        escolhidas = [r for r in linhas if self._passa(r)]
        if self._op == "update":
            for r in escolhidas:
                r.update(self._dados)
            return SimpleNamespace(data=escolhidas)
        return SimpleNamespace(data=escolhidas[: self._lim] if self._lim else escolhidas)


class _FakeSupabase:
    def __init__(self, db):
        self.db = db

    def table(self, nome):
        return _Q(self.db, nome)


CLIENTE = {
    "id": "c1", "nome": "Ana Exemplo", "telefone": "912345678", "email": None,
    "tipo_interesse": "compra", "orcamento": 250000, "zona_preferida": "Buarcos",
}


@pytest.fixture
def mundo(monkeypatch):
    db: dict = {"leads": [], "agente_tarefas": []}
    fake = _FakeSupabase(db)
    avisos: list[str] = []
    monkeypatch.setattr(tools, "get_supabase", lambda: fake)
    monkeypatch.setattr(guards, "get_supabase", lambda: fake)
    monkeypatch.setattr(guards, "notificar", lambda assunto, corpo, imovel_ref=None: avisos.append(assunto))

    def guardar(cliente=None, contexto=None, **inputs):
        cliente = dict(cliente or CLIENTE)
        cliente.update({k: v for k, v in inputs.items() if k in ("tipo_interesse", "orcamento", "zona_preferida")})

        async def _find_or_create(**kw):
            return cliente

        monkeypatch.setattr(tools, "find_or_create_cliente", _find_or_create)
        base = {"nome": cliente["nome"], "telefone": cliente["telefone"], "tipo_interesse": cliente["tipo_interesse"]}
        return asyncio.run(tools._guardar_dados_cliente(
            {**base, **inputs}, contexto or {"canal": "site", "agente": "a1_vendedor"},
        ))

    return db, avisos, guardar


# ── P1: contacto e tipo certos na lead ──────────────────────────────────────

@pytest.mark.parametrize("interesse, tipo", [
    ("compra", "compra"), ("arrendamento", "arrendamento"),
    ("venda", "angariacao"), ("recrutamento", "recrutamento"),
])
def test_lead_nasce_com_o_tipo_certo_e_o_contacto_na_linha(mundo, interesse, tipo):
    db, _, guardar = mundo
    guardar(tipo_interesse=interesse, orcamento=None)  # sem MQL completo: aqui só interessa o nascimento

    (lead,) = db["leads"]
    assert lead["tipo"] == tipo
    assert lead["origem"] == "assistente" and lead["estado"] == "nova"
    assert lead["telefone"] == "912345678" and lead["nome"] == "Ana Exemplo"
    assert "email" not in lead  # None não se escreve


@pytest.mark.parametrize("interesse", ["outro", "", None, "qualquer coisa"])
def test_outro_ou_vazio_nao_cria_lead(mundo, interesse):
    db, _, guardar = mundo
    guardar(tipo_interesse=interesse)
    assert db["leads"] == []


def test_lead_aberta_nao_duplica_e_liga_o_cliente(mundo):
    db, _, guardar = mundo
    db["leads"].append({"id": "meta-1", "estado": "contactada", "telefone": "912345678", "cliente_id": None})
    guardar()
    assert len(db["leads"]) == 1 and db["leads"][0]["cliente_id"] == "c1"


# ── P2: promoção depois de a lead existir ───────────────────────────────────

def test_mql_completo_no_chat_do_site_promove_a_lead_uma_so_vez(mundo):
    """O buraco do site: sem telefone de canal, `promover_se_qualificada` não corre, e a
    lead `nova` nunca era promovida (a de 17/09 continua `nova`)."""
    db, avisos, guardar = mundo
    guardar()

    (lead,) = db["leads"]
    assert lead["estado"] == "qualificada" and lead.get("qualificada_em")
    assert len(db["agente_tarefas"]) == 1 and "Lead qualificada" in db["agente_tarefas"][0]["titulo"]
    assert len(avisos) == 1

    guardar()  # o modelo repete a tool: não pode duplicar tarefa nem email
    assert len(db["agente_tarefas"]) == 1 and len(avisos) == 1


def test_a_tarefa_ja_nao_diz_lead_da_meta_quando_nao_e_da_meta(mundo):
    db, _, guardar = mundo
    guardar()
    assert "da Meta" not in db["agente_tarefas"][0]["descricao"]


def test_promove_arrendamento(mundo):
    db, avisos, guardar = mundo
    guardar(tipo_interesse="arrendamento")
    assert db["leads"][0]["estado"] == "qualificada" and len(avisos) == 1


@pytest.mark.parametrize("interesse", ["recrutamento", "venda"])
def test_recrutamento_e_venda_nao_promovem_mesmo_com_campos_de_mql(mundo, interesse):
    """Decisão 08/10: já têm o seu aviso (`escalar_para_humano`); promovê-los duplicava
    tarefas e emails, e um candidato nunca tem "orçamento"."""
    db, avisos, guardar = mundo
    guardar(tipo_interesse=interesse)
    assert db["leads"][0]["estado"] == "nova"
    assert db["agente_tarefas"] == [] and avisos == []


def test_mql_incompleto_nao_promove(mundo):
    db, avisos, guardar = mundo
    guardar(orcamento=None)
    assert db["leads"][0]["estado"] == "nova" and avisos == []


def test_promocao_encontra_a_lead_antiga_so_com_cliente_id(mundo):
    """As 25 leads existentes só têm `cliente_id`: tem de se encontrar por aí."""
    db, avisos, _ = mundo
    db["leads"].append({"id": "velha", "estado": "nova", "tipo": "compra", "origem": "assistente", "cliente_id": "c1"})
    guards.promover_lead_do_cliente(dict(CLIENTE), "a1_vendedor")
    assert db["leads"][0]["estado"] == "qualificada" and len(avisos) == 1


def test_lead_da_meta_continua_a_ser_promovida_pelo_telefone(mundo):
    """Regressão: o caminho antigo (`contactada`, telefone na linha) não muda."""
    db, avisos, _ = mundo
    db["leads"].append({"id": "m", "estado": "contactada", "tipo": "compra", "origem": "meta",
                        "telefone": "912345678", "cliente_id": None})
    guards._promover_lead(guards.get_supabase(), dict(CLIENTE))
    assert db["leads"][0]["estado"] == "qualificada"
    assert "da Meta" in db["agente_tarefas"][0]["descricao"]


def test_falha_na_promocao_nao_derruba_a_gravacao(mundo, monkeypatch):
    db, _, guardar = mundo

    def _rebenta(*a, **k):
        raise RuntimeError("base em baixo")

    monkeypatch.setattr(guards, "_promover_lead", _rebenta)
    assert "sucesso" in guardar()  # a lead ficou gravada, a promoção repete-se


# ── efeito sobre o routing ──────────────────────────────────────────────────

def test_candidata_registada_por_assistente_volta_a_ser_da_ines(mundo):
    """Antes a lead não tinha telefone: `lead_aberta` não a via e o router não a devolvia
    à Inês (nem à Bárbara). Com o `tipo` certo nunca vai parar à Matilde."""
    _, _, guardar = mundo
    guardar(tipo_interesse="recrutamento", contexto={"canal": "whatsapp", "agente": "a2_geral"})
    assert asyncio.run(guards.agente_de_lead("912345678")) == "a3_recrutamento"


def test_vendedor_registado_volta_a_ser_da_barbara(mundo):
    _, _, guardar = mundo
    guardar(tipo_interesse="venda", contexto={"canal": "whatsapp", "agente": "a2_geral"})
    assert asyncio.run(guards.agente_de_lead("912345678")) == "a4_angariador"
