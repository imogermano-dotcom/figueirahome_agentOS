import asyncio
from types import SimpleNamespace

from app.agents.broker import nudge


def test_e_despedida_reconhece_marcas():
    assert nudge._e_despedida("Cuide-se, Maria. Até quando precisar! 👋")
    assert nudge._e_despedida("Boa continuação, João! 😊")
    assert nudge._e_despedida("De nada, Rogério. Muita força! 🙏")


def test_e_despedida_nao_marca_pergunta_normal():
    assert not nudge._e_despedida("Antes de lhe dar o preço, só duas perguntas rápidas:")
    assert not nudge._e_despedida("")
    assert not nudge._e_despedida(None)


class _FakeTable:
    def __init__(self, nome, estado):
        self.nome, self.estado = nome, estado

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def is_(self, *a, **k):
        return self

    def gte(self, *a, **k):
        return self

    def lte(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def in_(self, campo, valores):
        if self.nome == "leads" and campo == "telefone":
            self._telefone_pedido = valores[0]
        return self

    def update(self, dados):
        self.estado["updates"].append((self.nome, dados))
        return self

    def insert(self, dados):
        self.estado["inserts"].append((self.nome, dados))
        return self

    def execute(self):
        if self.nome == "leads":
            lead = self.estado["leads_por_participante"].get(getattr(self, "_telefone_pedido", None))
            return SimpleNamespace(data=[lead] if lead else [])
        return SimpleNamespace(data=self.estado.get("conversas", []))


class _FakeSupabase:
    def __init__(self, estado):
        self.estado = estado

    def table(self, nome):
        return _FakeTable(nome, self.estado)


def _montar(monkeypatch, conversas, leads_por_participante):
    estado = {"conversas": conversas, "leads_por_participante": leads_por_participante, "updates": [], "inserts": []}
    monkeypatch.setattr(nudge, "get_supabase", lambda: _FakeSupabase(estado))

    # Decisão testada aqui é a de `_pode_enviar` (fecho/contacto_humano_em),
    # não a normalização de telefone — já coberta nos testes de `guards`.
    monkeypatch.setattr(nudge.guards, "normalizar_telefone", lambda t: t)
    monkeypatch.setattr(nudge.guards, "variantes_telefone", lambda n: [n])

    async def _fake_send(to, texto):
        estado.setdefault("enviados", []).append((to, texto))

    monkeypatch.setattr(nudge.meta_api, "send_text_message", _fake_send)

    async def _fake_save(conversa_id, canal, participante, mensagens, agente=None):
        estado.setdefault("gravados", []).append(conversa_id)
        return conversa_id

    monkeypatch.setattr(nudge, "save_conversation", _fake_save)
    return estado


def _conversa(id_, participante, ultimo_texto="Antes de lhe dar o preço, diga-me só:"):
    return {
        "id": id_, "participante": participante,
        "mensagens": [{"role": "user", "timestamp": "t", "content": "oi"},
                      {"role": "assistant", "timestamp": "t", "content": ultimo_texto}],
    }


def test_candidato_elegivel_e_enviado(monkeypatch):
    conversas = [_conversa("c1", "351900000001")]
    leads = {"351900000001": {"estado": "contactada", "contacto_humano_em": None}}
    estado = _montar(monkeypatch, conversas, leads)

    resumo = asyncio.run(nudge.enviar_nudges(nudge.A1))

    assert resumo == {"candidatos": 1, "enviados": 1, "erros": 0}
    assert estado["enviados"] == [("351900000001", nudge.TEXTO_NUDGE)]
    assert estado["gravados"] == ["c1"]
    assert estado["updates"][0][0] == "agente_conversas"
    assert "nudge_em" in estado["updates"][0][1]


def test_sem_lead_nenhuma_ainda_recebe_nudge(monkeypatch):
    """O caso que motivou a Frente A: quem nunca chegou a ter `leads` (ex.
    fez uma proposta mas nunca deu nome/telefone) não pode ficar de fora só
    por não haver registo — é precisamente quem mais precisa do nudge."""
    conversas = [_conversa("c1", "351900000001")]
    estado = _montar(monkeypatch, conversas, {})  # nenhuma lead para este número

    resumo = asyncio.run(nudge.enviar_nudges(nudge.A1))

    assert resumo == {"candidatos": 1, "enviados": 1, "erros": 0}
    assert estado["enviados"] == [("351900000001", nudge.TEXTO_NUDGE)]


def test_despedida_nao_recebe_nudge(monkeypatch):
    conversas = [_conversa("c1", "351900000001", ultimo_texto="Cuide-se, boa continuação! 👋")]
    leads = {"351900000001": {"estado": "contactada", "contacto_humano_em": None}}
    estado = _montar(monkeypatch, conversas, leads)

    resumo = asyncio.run(nudge.enviar_nudges(nudge.A1))

    assert resumo == {"candidatos": 0, "enviados": 0, "erros": 0}
    assert "enviados" not in estado


def test_lead_com_contacto_humano_nao_recebe_nudge(monkeypatch):
    conversas = [_conversa("c1", "351900000001")]
    leads = {"351900000001": {"estado": "contactada", "contacto_humano_em": "2026-09-01T00:00:00Z"}}
    _montar(monkeypatch, conversas, leads)

    resumo = asyncio.run(nudge.enviar_nudges(nudge.A1))

    assert resumo == {"candidatos": 0, "enviados": 0, "erros": 0}


def test_lead_fechada_nao_recebe_nudge(monkeypatch):
    conversas = [_conversa("c1", "351900000001")]
    leads = {"351900000001": {"estado": "engano", "contacto_humano_em": None}}
    _montar(monkeypatch, conversas, leads)

    resumo = asyncio.run(nudge.enviar_nudges(nudge.A1))

    assert resumo == {"candidatos": 0, "enviados": 0, "erros": 0}


def test_a3_a4_sem_guarda_nao_bloqueiam_por_leads(monkeypatch):
    """Inês/Bárbara não têm `_pode_enviar_a1` associada — mesmo com uma
    lead 'fechada' registada nesse número (de um contacto totalmente
    diferente), o candidato passa; só a despedida trava."""
    conversas = [_conversa("c1", "351900000002")]
    leads = {"351900000002": {"estado": "engano", "contacto_humano_em": None}}
    estado = _montar(monkeypatch, conversas, leads)

    resumo = asyncio.run(nudge.enviar_nudges(nudge.A3))

    assert resumo == {"candidatos": 1, "enviados": 1, "erros": 0}
    assert estado["enviados"] == [("351900000002", nudge.TEXTO_NUDGE_A3)]


def test_enviar_todos_nudges_agrega_os_3(monkeypatch):
    conversas = [_conversa("c1", "351900000003")]
    estado = _montar(monkeypatch, conversas, {})

    resumo = asyncio.run(nudge.enviar_todos_nudges())

    assert set(resumo.keys()) == {nudge.A1, nudge.A3, nudge.A4}
    for parcial in resumo.values():
        assert set(parcial.keys()) == {"candidatos", "enviados", "erros"}
