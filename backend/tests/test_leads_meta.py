"""Leads da Meta — semeadura da conversa e qualificação.

Corre sem base de dados: o cliente Supabase é substituído por um duplo em
memória. O que se testa aqui é o que decide se uma lead paga chega ao A1 ou se
cai no A2 sem ninguém dar por isso.

    pytest backend/tests/test_leads_meta.py      (a partir de `backend/`)
"""

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker.conversation import _participantes  # noqa: E402
from app.agents.broker.guards import lead_qualificada  # noqa: E402
from app.api.leads_meta import _campos_mql  # noqa: E402


# ── qualificação ────────────────────────────────────────────────────────────

def test_mql_exige_os_tres_campos():
    completo = {"tipo_interesse": "compra", "orcamento": 200000, "zona_preferida": "Buarcos"}
    assert lead_qualificada(completo) is True

    for em_falta in ("tipo_interesse", "orcamento", "zona_preferida"):
        parcial = dict(completo)
        parcial.pop(em_falta)
        assert lead_qualificada(parcial) is False, f"{em_falta} devia ser obrigatório"

    assert lead_qualificada({**completo, "zona_preferida": ""}) is False  # vazio não conta
    assert lead_qualificada(None) is False
    assert lead_qualificada({}) is False


def test_prazo_compra_nao_entra_no_mql():
    """`prazo_compra` só é recolhido no gate das landing pages (migration 0020).
    Exigi-lo aqui deixava toda a lead de WhatsApp por qualificar."""
    assert lead_qualificada(
        {"tipo_interesse": "compra", "orcamento": 200000, "zona_preferida": "Buarcos"}
    ) is True


def test_ficha_mapeada_para_os_campos_do_perfil():
    """`engine._perfil_cliente` lê estes três nomes e mais nenhum — se a ficha
    não aterrar aqui, o A1 volta a perguntar o que o formulário já respondeu."""
    assert _campos_mql({
        "tipo_interesse": "compra", "orcamento": "250000", "zona_preferida": "Tavarede",
    }) == {"tipo_interesse": "compra", "orcamento": "250000", "zona_preferida": "Tavarede"}

    # alias vindos do que `leads_angariacao` já usava
    assert _campos_mql({"tipo_imovel": "Moradia", "freguesia": "Lavos"}) == {
        "tipo_interesse": "Moradia", "zona_preferida": "Lavos",
    }

    assert _campos_mql({}) == {}
    assert _campos_mql({"orcamento": ""}) == {}   # vazio não sobrepõe
    assert _campos_mql(None) == {}


# ── a thread tem de ser encontrada ──────────────────────────────────────────

def test_conversa_semeada_e_encontrada_em_qualquer_formato():
    """O ponto que parte tudo silenciosamente: a Meta manda `351912345678` no
    webhook, nós semeamos o número normalizado. Um `.eq()` exacto não encontrava
    a thread semeada e a lead caía no A2 — que é o que a semeadura evita."""
    esperado = {"912345678", "351912345678", "+351912345678", "00351912345678"}
    for forma in ("351912345678", "912345678", "+351 912 345-678", "00351912345678"):
        assert esperado <= set(_participantes("whatsapp", forma)), forma


def test_participantes_nao_mexe_noutros_canais():
    """O banco de ensaio do painel usa `painel_a1_vendedor` como participante —
    normalizar isso como telefone dava lixo."""
    assert _participantes("painel", "painel_a1_vendedor") == ["painel_a1_vendedor"]
    assert _participantes("web", "sessao-123") == ["sessao-123"]


# ── endpoint ────────────────────────────────────────────────────────────────

LEAD = {
    "id": "11111111-1111-1111-1111-111111111111",
    "tipo": "compra",
    "estado": "nova",
    "nome": "Isabel Braga",
    "telefone": "912345678",
    "email": "isabel@exemplo.pt",
    "ficha": {"tipo_interesse": "compra", "orcamento": "250000", "zona_preferida": "Buarcos"},
    "cliente_id": None,
    "conversa_id": None,
}


class _FakeQuery:
    def __init__(self, tabela, estado):
        self.tabela, self.estado = tabela, estado
        self._dados = []

    def select(self, *a, **k):
        # O cliente é procurado por variantes do telefone, não por `eq` — tanto
        # no dedup como em `promover_se_qualificada`. Responde-se já aqui.
        if self.tabela == "agente_clientes" and self.estado.get("cliente"):
            self._dados = [self.estado["cliente"]]
        return self

    def update(self, dados):
        self.estado["updates"].append((self.tabela, dados))
        # A promoção tem de ser visível na chamada seguinte, senão a
        # idempotência não se consegue testar.
        if self.tabela == "leads" and self.estado.get("lead"):
            self.estado["lead"].update(dados)
        return self

    def insert(self, dados):
        self.estado["inserts"].append((self.tabela, dados))
        self._dados = [{"id": "novo-id", **(dados if isinstance(dados, dict) else {})}]
        return self

    def eq(self, campo, valor):
        if self.tabela == "leads" and campo == "id":
            self._dados = [self.estado["lead"]]
        return self

    def in_(self, campo=None, valores=None, *a, **k):
        if self.tabela == "leads" and campo == "estado":
            lead = self.estado.get("lead")
            self._dados = [lead] if lead and lead.get("estado") in valores else []
        return self

    def neq(self, *a, **k):
        return self

    def gte(self, *a, **k):
        return self

    def ilike(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def execute(self):
        from types import SimpleNamespace
        return SimpleNamespace(data=self._dados)


class _FakeSupabase:
    def __init__(self, estado):
        self.estado = estado

    def table(self, nome):
        return _FakeQuery(nome, self.estado)


@pytest.fixture
def cliente_e_estado(monkeypatch):
    estado = {"lead": dict(LEAD), "inserts": [], "updates": []}
    fake = _FakeSupabase(estado)

    import app.agents.broker.conversation as conversation
    import app.agents.broker.guards as guards
    import app.api.leads_meta as leads_meta
    from app.api.deps import require_automacao_access
    from app.main import app

    for modulo in (leads_meta, guards, conversation):
        monkeypatch.setattr(modulo, "get_supabase", lambda: fake)

    app.dependency_overrides[require_automacao_access] = lambda: "teste"
    yield TestClient(app), estado
    app.dependency_overrides.clear()


def test_semeadura_cria_thread_do_a1_com_o_template_no_historico(cliente_e_estado):
    client, estado = cliente_e_estado
    r = client.post(
        f"/api/leads/{LEAD['id']}/conversa-semeada",
        json={"template": "Olá Isabel, recebemos o seu pedido sobre imóveis na Figueira."},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ja_existia"] is False

    conversas = [d for t, d in estado["inserts"] if t == "agente_conversas"]
    assert conversas, "não semeou conversa nenhuma"
    conversa = conversas[0]

    # Sem isto o router decide por regex e um "Sim" vai para o A2.
    assert conversa["agente"] == "a1_vendedor"
    # O template entra como nosso: o A1 lê-o como já dito e não repete.
    assert conversa["mensagens"][0]["role"] == "assistant"
    assert "Isabel" in conversa["mensagens"][0]["content"]
    # Participante normalizado — o webhook encontra-o pelas variantes.
    assert conversa["participante"] == "912345678"


def test_semeadura_nao_qualifica_lead_que_ainda_nao_respondeu(cliente_e_estado):
    """O formulário Meta traz os três campos do MQL, e a semeadura passa-os a
    `find_or_create_cliente`. Sem cuidado, a lead era promovida e criava tarefa
    antes de a pessoa responder — e o `contactada` que o endpoint escreve a
    seguir apagava a promoção na mesma. Qualificar é o que acontece na conversa."""
    client, estado = cliente_e_estado
    r = client.post(f"/api/leads/{LEAD['id']}/conversa-semeada", json={"template": "olá"})
    assert r.status_code == 200

    assert not [d for t, d in estado["inserts"] if t == "agente_tarefas"], \
        "criou tarefa de lead qualificada antes de a lead responder"
    leads_updates = [d for t, d in estado["updates"] if t == "leads"]
    assert leads_updates and leads_updates[-1]["estado"] == "contactada"


def test_angariacao_nao_e_seguida_pelo_a1(cliente_e_estado):
    """O A4 está adiado; angariação continua com a consultora ao telefone."""
    client, estado = cliente_e_estado
    estado["lead"]["tipo"] = "angariacao"
    r = client.post(f"/api/leads/{LEAD['id']}/conversa-semeada", json={"template": "olá"})
    assert r.status_code == 422
    assert not [d for t, d in estado["inserts"] if t == "agente_conversas"]


def test_lead_sem_telefone_recusada(cliente_e_estado):
    client, estado = cliente_e_estado
    estado["lead"]["telefone"] = None
    r = client.post(f"/api/leads/{LEAD['id']}/conversa-semeada", json={"template": "olá"})
    assert r.status_code == 422


def test_semeadura_e_idempotente(cliente_e_estado):
    """O n8n pode repetir a chamada; repetir não pode duplicar a thread nem
    reescrever o histórico de uma conversa a decorrer."""
    client, estado = cliente_e_estado
    estado["lead"]["conversa_id"] = "conversa-ja-existente"
    r = client.post(f"/api/leads/{LEAD['id']}/conversa-semeada", json={"template": "olá"})
    assert r.status_code == 200
    assert r.json()["ja_existia"] is True
    assert not [d for t, d in estado["inserts"] if t == "agente_conversas"]


def test_lead_inexistente_da_404(cliente_e_estado):
    client, estado = cliente_e_estado
    estado["lead"] = None

    class _Vazio(_FakeQuery):
        def eq(self, campo, valor):
            self._dados = []
            return self

    import app.api.leads_meta as leads_meta
    leads_meta.get_supabase = lambda: type("S", (), {"table": lambda s, n: _Vazio(n, estado)})()
    r = client.post(f"/api/leads/{LEAD['id']}/conversa-semeada", json={"template": "olá"})
    assert r.status_code == 404


def test_endpoint_exige_segredo():
    """Sem override da dependência: o Make/n8n sem `X-Automacao-Secret` (nem JWT)
    não entra."""
    from app.main import app

    r = TestClient(app).post(
        f"/api/leads/{LEAD['id']}/conversa-semeada", json={"template": "olá"}
    )
    assert r.status_code == 401


# ── promoção ao fim do turno ────────────────────────────────────────────────

CLIENTE = {
    "id": "cliente-1",
    "nome": "Isabel Braga",
    "telefone": "912345678",
    "email": "isabel@exemplo.pt",
    "tipo_interesse": "compra",
    "orcamento": 250000,
    "zona_preferida": "Buarcos",
}


@pytest.fixture
def promocao(monkeypatch):
    """`guards` com Supabase falso. Devolve `(correr, estado)`."""
    import app.agents.broker.guards as guards

    estado = {"lead": dict(LEAD), "cliente": dict(CLIENTE), "inserts": [], "updates": []}
    monkeypatch.setattr(guards, "get_supabase", lambda: _FakeSupabase(estado))

    def correr():
        asyncio.run(guards.promover_se_qualificada(CLIENTE["telefone"]))

    return correr, estado


def _tarefas(estado):
    return [d for t, d in estado["inserts"] if t == "agente_tarefas"]


def test_lead_com_perfil_completo_e_promovida_ao_fim_do_turno(promocao):
    """O buraco que esta função fecha: com o MQL vindo do formulário o A1 não
    tem dados para escrever, `find_or_create_cliente` nunca corre, e sem este
    gatilho a lead ficava `contactada` para sempre — o corretor nunca sabia."""
    correr, estado = promocao
    estado["lead"]["estado"] = "contactada"

    correr()

    assert estado["lead"]["estado"] == "qualificada"
    assert estado["lead"]["qualificada_em"]
    assert len(_tarefas(estado)) == 1
    assert "Buarcos" in _tarefas(estado)[0]["descricao"]


def test_lead_nova_tambem_promove_no_fim_do_turno(promocao):
    """`whatsapp_permissao` está a `True` em 3 de 79: a maioria não recebe
    template, fica `nova` e o n8n nunca semeia. Se escrever na mesma, o turno é
    prova de que respondeu — ao contrário da semeadura, que corre antes disso."""
    correr, estado = promocao
    assert estado["lead"]["estado"] == "nova"

    correr()

    assert estado["lead"]["estado"] == "qualificada"
    assert len(_tarefas(estado)) == 1


def test_perfil_incompleto_nao_promove(promocao):
    """MQL = orçamento + zona + tipo. Faltando um, não se toca na lead."""
    correr, estado = promocao
    estado["cliente"].pop("orcamento")

    correr()

    assert not [d for t, d in estado["updates"] if t == "leads"]
    assert not _tarefas(estado)


def test_promocao_nao_repete(promocao):
    """Corre a cada turno de WhatsApp: promovida uma vez, o estado deixa de bater
    no filtro e não há segunda tarefa para o mesmo corretor."""
    correr, estado = promocao
    estado["lead"]["estado"] = "contactada"

    correr()
    correr()

    assert len(_tarefas(estado)) == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
