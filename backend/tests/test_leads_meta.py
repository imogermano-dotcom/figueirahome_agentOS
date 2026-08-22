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
from app.agents.broker.guards import (  # noqa: E402
    campos_mql_da_ficha as _campos_mql,
    lead_qualificada,
)


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
        self._pendente = None

    def select(self, *a, **k):
        # O cliente é procurado por variantes do telefone, não por `eq` — tanto
        # no dedup como em `promover_se_qualificada`. Responde-se já aqui.
        if self.tabela == "agente_clientes" and self.estado.get("cliente"):
            self._dados = [self.estado["cliente"]]
        return self

    def update(self, dados):
        # Adiado até ao `execute()`: no PostgREST o `update` vem antes dos
        # filtros, e aplicar já aqui fazia o duplo escrever em linhas que a query
        # real nunca tocaria — era impossível testar um `.in_("estado", ...)`
        # restritivo, que é exactamente a guarda de `encerrar_lead_do_telefone`.
        self._pendente = dados
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
        # Um update só conta se os filtros deixaram alguma linha de pé — é assim
        # que o Postgres se comporta, e é a diferença entre "a lead fechou" e
        # "reescrevi uma lead que já estava fechada".
        if self._pendente is not None and self._dados:
            self.estado["updates"].append((self.tabela, self._pendente))
            if self.tabela == "leads" and self.estado.get("lead"):
                # A escrita tem de ser visível na chamada seguinte, senão a
                # idempotência não se consegue testar.
                self.estado["lead"].update(self._pendente)
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


def test_promocao_avisa_o_corretor_com_o_que_ele_precisa(promocao, monkeypatch):
    """A tarefa é o registo; o aviso é o toque no ombro. Tem de chegar com o
    telefone e o MQL, senão o corretor abre o painel na mesma e não valeu."""
    import app.agents.broker.guards as guards

    avisos = []
    monkeypatch.setattr(
        guards, "notificar",
        lambda a, c, imovel_ref=None: avisos.append((a, c, imovel_ref)),
    )

    correr, estado = promocao
    estado["lead"]["estado"] = "contactada"
    estado["lead"]["imovel_ref"] = "FH2581"
    correr()

    assert len(avisos) == 1
    assunto, corpo, imovel = avisos[0]
    assert "Isabel Braga" in assunto
    for esperado in ("912345678", "250000", "Buarcos", "compra"):
        assert esperado in corpo, f"falta {esperado} no aviso"
    # O imóvel do anúncio é o que decide qual a consultora avisada.
    assert imovel == "FH2581"
    assert "FH2581" in corpo


def test_promocao_nao_repete(promocao):
    """Corre a cada turno de WhatsApp: promovida uma vez, o estado deixa de bater
    no filtro e não há segunda tarefa para o mesmo corretor."""
    correr, estado = promocao
    estado["lead"]["estado"] = "contactada"

    correr()
    correr()

    assert len(_tarefas(estado)) == 1


# ── contexto sem semeadura ──────────────────────────────────────────────────
#
# O fluxo real não passa por endpoint nenhum nosso: Make escreve a lead, n8n
# manda o template, e o A1 só entra quando a pessoa responde. Nessa altura
# `agente_clientes` ainda não tem linha — o que o formulário respondeu está em
# `leads.ficha`, e o que já lhe foi dito em `leads.template_enviado`.

import app.agents.broker.engine as engine  # noqa: E402

FICHA = {"tipo_interesse": "compra", "orcamento": "250000", "zona_preferida": "Buarcos"}


def _contexto(monkeypatch, *, cliente="", lead=None, thread_nova=True):
    monkeypatch.setattr(engine, "_perfil_cliente", lambda tel: cliente)

    async def _lead(_tel):
        return lead

    monkeypatch.setattr(engine, "lead_aberta", _lead)
    perfil, template, _lead_devolvida = asyncio.run(
        engine._contexto_inicial("912345678", thread_nova=thread_nova)
    )
    return perfil, template


def test_perfil_vem_da_ficha_quando_nao_ha_cliente(monkeypatch):
    """O caso central: sem semeadura, `agente_clientes` está vazio e o A1
    perguntaria outra vez o que a pessoa acabou de escrever no formulário."""
    perfil, _ = _contexto(
        monkeypatch, lead={"nome": "Isabel Braga", "ficha": FICHA, "template_enviado": None}
    )
    assert "Isabel Braga" in perfil
    assert "250000" in perfil and "Buarcos" in perfil
    assert "não voltes a pedir dados que já temos" in perfil


def test_cliente_ganha_a_ficha(monkeypatch):
    """`agente_clientes` é escrita durante a conversa, logo é mais recente. Se a
    ficha se sobrepusesse, um orçamento corrigido ao A1 seria ressuscitado pelo
    valor inicial do formulário."""
    perfil, _ = _contexto(
        monkeypatch,
        cliente="\n\nEste cliente já está registado: Orçamento: 400000",
        lead={"nome": "Isabel", "ficha": FICHA, "template_enviado": None},
    )
    assert "400000" in perfil
    assert "250000" not in perfil


# ── apresentação da Matilde, uma só vez ─────────────────────────────────────
#
# O template da Meta é enviado pelo n8n e gravado em `leads.template_enviado`.
# Se ele já disser quem é a assistente, repetir "Sou a Matilde" na resposta
# seguinte soa a robô partido; se não disser e a A1 também não, a pessoa nunca
# fica a saber com quem fala. Deixar o modelo inferir do histórico dava as duas
# falhas — daí a instrução ser explícita e calculada aqui.


def test_apresentacao_prefixada_quando_o_modelo_falha():
    """Medido a 2026-08-22 em 7 conversas reais: o modelo apresentou-se em 4. A
    Ana Luísa, o Pedro Marques e o Jorge Pessoa falaram com uma IA sem lho ser
    dito, apesar de a instrução ter sido injectada nas sete. É transparência, não
    estilo — e por isso deixou de estar ao critério do modelo."""
    from app.agents.broker.assistants import A1, APRESENTACAO_A1

    template = {"role": "assistant", "content": "Olá Ana, fala da Figueirahome."}
    resposta = engine._garantir_apresentacao(
        "Claro, Ana! O imóvel do seu anúncio é este: …", A1, True, [template]
    )
    assert resposta.startswith(APRESENTACAO_A1)
    assert "O imóvel do seu anúncio" in resposta


def test_nao_duplica_quando_o_modelo_ja_se_apresentou():
    from app.agents.broker.assistants import A1, APRESENTACAO_A1

    ja = f"{APRESENTACAO_A1}\n\nOlá Teresa! Encontrei a ficha."
    assert engine._garantir_apresentacao(ja, A1, True, []) == ja


def test_nao_duplica_quando_o_template_ja_apresentou():
    """O template do n8n é o outro sítio de onde a apresentação pode vir."""
    from app.agents.broker.assistants import A1

    template = {"role": "assistant", "content": "Olá, sou a Matilde da FigueiraHome."}
    resposta = engine._garantir_apresentacao("Claro! A ficha é esta.", A1, True, [template])
    assert resposta == "Claro! A ficha é esta."


def test_apresentacao_so_no_primeiro_turno_e_so_na_a1():
    """A A2 não tem nome atribuído, e a meio da conversa seria absurdo."""
    from app.agents.broker.assistants import A1, A2

    assert engine._garantir_apresentacao("Sim.", A1, False, []) == "Sim."
    assert engine._garantir_apresentacao("Sim.", A2, True, []) == "Sim."


def test_erro_nao_leva_apresentacao():
    """Prefixar a mensagem de avaria seria pior do que a avaria."""
    from app.agents.broker.assistants import A1

    assert engine._garantir_apresentacao(engine._ERRO, A1, True, []) == engine._ERRO


def test_prompt_manda_responder_antes_de_qualificar():
    """O Pedro Marques perguntou pela documentação de financiamento e recebeu as
    duas perguntas do guião, sem resposta nenhuma (2026-08-22)."""
    from app.agents.broker.assistants import _PROMPT_A1

    assert "RESPONDE PRIMEIRO AO QUE TE PERGUNTAM" in _PROMPT_A1
    assert "nunca em vez da resposta" in _PROMPT_A1


def test_apresenta_se_quando_o_template_nao_a_identificou(monkeypatch):
    """O template em uso a 2026-08-18 diz só "Fala da Figueirahome"."""
    perfil, _ = _contexto(monkeypatch, lead={
        "nome": "Isabel", "ficha": FICHA,
        "template_enviado": "Olá Isabel,\nFala da Figueirahome.\nEm que posso ser útil?",
    })
    assert "Sou a Matilde, assistente virtual da FigueiraHome." in perfil
    assert "não voltes a apresentar-te" not in perfil


def test_nao_repete_a_apresentacao_se_o_template_ja_a_fez(monkeypatch):
    perfil, _ = _contexto(monkeypatch, lead={
        "nome": "Isabel", "ficha": FICHA,
        "template_enviado": "Olá Isabel, sou a Matilde, assistente virtual da FigueiraHome.",
    })
    assert "não voltes a apresentar-te" in perfil
    assert "Começa a tua resposta" not in perfil


def test_sem_template_gravado_manda_o_prompt_decidir(monkeypatch):
    """As 108 leads anteriores ao fluxo do n8n têm `template_enviado` a NULL —
    não se sabe o que lhes foi dito. Sem instrução injectada, vale a regra geral
    do prompt: apresentar-se na primeira mensagem."""
    perfil, msg = _contexto(monkeypatch, lead={
        "nome": "Isabel", "ficha": FICHA, "template_enviado": None,
    })
    assert msg is None
    assert "Matilde" not in perfil


def test_template_entra_so_no_primeiro_turno(monkeypatch):
    lead = {"nome": "Isabel", "ficha": FICHA, "template_enviado": "Olá Isabel, recebemos o seu pedido."}

    _, msg = _contexto(monkeypatch, lead=lead, thread_nova=True)
    assert msg["role"] == "assistant"
    assert "recebemos o seu pedido" in msg["content"]

    # No turno seguinte já está no histórico gravado — injectar outra vez
    # duplicava a mensagem na conversa.
    _, msg = _contexto(monkeypatch, lead=lead, thread_nova=False)
    assert msg is None


def test_sem_lead_aberta_nada_muda(monkeypatch):
    """Quem escreve sem ser lead da Meta continua a ser tratado como sempre."""
    perfil, msg = _contexto(monkeypatch, lead=None)
    assert perfil == ""
    assert msg is None


def test_lead_sem_template_nao_injecta(monkeypatch):
    """A lead pode existir sem o n8n ter chegado a enviar nada."""
    _, msg = _contexto(monkeypatch, lead={"nome": "Isabel", "ficha": FICHA, "template_enviado": None})
    assert msg is None


def test_imovel_do_anuncio_entra_no_contexto(monkeypatch):
    """Visto ao vivo (2026-08-16, FH2581): a pessoa escreveu "quero saber mais
    acerca deste imóvel" e o A1 pediu-lhe a referência — a quem tinha acabado de
    clicar no anúncio desse imóvel. O `leads.imovel_ref` diz qual é."""
    perfil, _ = _contexto(
        monkeypatch,
        lead={"nome": "Isabel", "ficha": {}, "template_enviado": None, "imovel_ref": "FH2581"},
    )
    assert "FH2581" in perfil
    assert "Não lhe peças a referência" in perfil


def test_sem_imovel_no_anuncio_nao_inventa(monkeypatch):
    """Nem toda a lead vem de um anúncio de imóvel específico."""
    perfil, _ = _contexto(
        monkeypatch,
        lead={"nome": "Isabel", "ficha": FICHA, "template_enviado": None, "imovel_ref": None},
    )
    assert "anúncio do imóvel" not in perfil


def test_forcing_escolhe_ficha_quando_a_lead_traz_imovel():
    """`_SEARCH_RE` inclui "imóvel", portanto a primeira frase de uma lead da
    Meta — "quero saber mais acerca deste imóvel" — forçava `pesquisar_imoveis`
    sem critérios nenhuns. Medido ao vivo: chamada com `{}`, resposta
    descartada, e uma iteração inteira perdida na resposta que decide se a
    pessoa continua a conversa."""
    from app.agents.broker.assistants import ASSISTENTES

    forcar = ASSISTENTES["a1_vendedor"]["force"]
    msg = "quero saber mais acerca deste imóvel"
    assert forcar[1].search(msg), "o regex tem de bater, senão o teste não prova nada"

    def escolher(thread_nova, lead):
        forcar_agora = bool(forcar and forcar[1].search(msg))
        tool = forcar[0] if forcar_agora else None
        if thread_nova and forcar_agora and lead and lead.get("imovel_ref"):
            tool = "ficha_imovel"
        return tool

    assert escolher(True, {"imovel_ref": "FH2581"}) == "ficha_imovel"
    # Turno seguinte: "e tem T2 mais baratos?" volta a ser pesquisa.
    assert escolher(False, {"imovel_ref": "FH2581"}) == "pesquisar_imoveis"
    # Lead sem imóvel no anúncio, ou quem não é lead, mantém o comportamento.
    assert escolher(True, {"imovel_ref": None}) == "pesquisar_imoveis"
    assert escolher(True, None) == "pesquisar_imoveis"


def test_contexto_devolve_a_lead_para_o_motor_a_marcar(monkeypatch):
    """O motor precisa da lead no fim do turno para registar que ela respondeu.
    Vem daqui, que já a leu — sem consulta extra."""
    lead = {"id": "lead-1", "nome": "Isabel", "ficha": FICHA, "template_enviado": None}
    monkeypatch.setattr(engine, "_perfil_cliente", lambda tel: "")

    async def _lead(_tel):
        return lead

    monkeypatch.setattr(engine, "lead_aberta", _lead)
    _, _, devolvida = asyncio.run(engine._contexto_inicial("912345678", thread_nova=True))
    assert devolvida["id"] == "lead-1"


def test_marcar_resposta_so_escreve_na_primeira_vez(monkeypatch):
    """`respondeu_em` guarda o PRIMEIRO turno. O filtro `is null` faz isso e
    poupa a leitura — se desaparecer, cada mensagem reescreve a data e o
    follow-up perde a noção de há quanto tempo a lead fala connosco."""
    import app.agents.broker.guards as guards

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

    monkeypatch.setattr(guards, "get_supabase",
                        lambda: type("S", (), {"table": lambda s, n: _Q()})())

    asyncio.run(guards.marcar_lead_respondeu("lead-1", "conversa-9"))

    assert chamadas["id"] == "lead-1"
    assert chamadas["filtro_is"] == ("respondeu_em", "null"), "sem isto reescreve a cada turno"
    assert chamadas["dados"]["conversa_id"] == "conversa-9"
    assert chamadas["dados"]["respondeu_em"]


def test_ficha_vazia_nao_inventa_perfil(monkeypatch):
    """Se os alias de `_ALIAS_FICHA` não baterem com os campos reais do
    formulário, o resultado é perfil vazio — não uma frase truncada."""
    perfil, _ = _contexto(monkeypatch, lead={"nome": None, "ficha": {"campo_desconhecido": "x"}})
    assert perfil == ""


# ══════════════════════════════════════════════════════════════
# Desfecho "Engano" (spec §2.2) — `encerrar_lead_do_telefone`
# ══════════════════════════════════════════════════════════════


@pytest.fixture
def encerramento(monkeypatch):
    """`guards` com Supabase falso. Devolve `(fechar, estado)`."""
    import app.agents.broker.guards as guards

    estado = {"lead": dict(LEAD), "cliente": None, "inserts": [], "updates": []}
    monkeypatch.setattr(guards, "get_supabase", lambda: _FakeSupabase(estado))

    def fechar(motivo="engano", nota=None):
        return asyncio.run(
            guards.encerrar_lead_do_telefone(LEAD["telefone"], motivo, nota)
        )

    return fechar, estado


def test_engano_fecha_a_lead_e_nao_faz_mais_nada(encerramento):
    """A spec diz "Regista o contacto com o estado engano. Sem mais ações" — e é
    à letra. Uma tarefa aqui punha o corretor a ligar a quem acabou de dizer que
    foi engano, que é o oposto do desfecho."""
    fechar, estado = encerramento

    assert fechar("engano", "disse que é número errado") is True

    assert estado["lead"]["estado"] == "engano"
    assert estado["lead"]["notas"] == "disse que é número errado"
    assert not estado["inserts"], "sem tarefa, sem cliente: 'sem mais ações'"


def test_lead_ja_fechada_nao_e_reescrita(encerramento):
    """Segunda chamada sobre uma lead já fechada não lhe muda o motivo — o
    filtro `estado in _ESTADOS_LEAD_ABERTA` é o que garante isso."""
    fechar, estado = encerramento
    estado["lead"]["estado"] = "fechada"

    assert fechar("engano") is False
    assert estado["lead"]["estado"] == "fechada"
    assert not [d for t, d in estado["updates"] if t == "leads"]


def test_lead_sem_resposta_ainda_pode_ser_encerrada(encerramento):
    """`sem_resposta` é estado aberto: quem responde tarde a dizer que foi
    engano tem de conseguir fechar na mesma."""
    fechar, estado = encerramento
    estado["lead"]["estado"] = "sem_resposta"

    assert fechar("engano") is True
    assert estado["lead"]["estado"] == "engano"


def test_motivo_desconhecido_nao_escreve_nada(encerramento):
    """O enum da tool é a fronteira, mas o modelo escolhe o valor. Um motivo
    fora da lista não pode inventar um estado que o painel não conhece."""
    fechar, estado = encerramento

    assert fechar("aborrecido") is False
    assert not estado["updates"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
