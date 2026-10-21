"""Satisfação pós-venda — A5 "Sofia" (docs/fases/satisfacao-pos-venda-plano.md).

O que não pode falhar:
* o inquérito em curso ganha o encaminhamento a uma lead antiga aberta (a resposta "9" não pode ir
  para a Matilde);
* quem decide o passo seguinte é o servidor (`fn_satisf_registar`): nota baixa e rescisão escalam
  uma vez e não recebem links; nota alta recebe exactamente os links que o servidor devolveu;
* o envio só sai para telemóveis portugueses e semeia a conversa com o texto do template.

Corre com `pytest backend/tests/`.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.agents.broker.engine as engine  # noqa: E402
import app.agents.broker.guards as guards  # noqa: E402
import app.agents.broker.satisfacao as satisfacao  # noqa: E402
import app.agents.broker.tools as tools  # noqa: E402
from app.agents.broker.assistants import A5, ASSISTENTES  # noqa: E402
from app.agents.broker.channels.whatsapp import meta_api  # noqa: E402

CONTEXTO = {"canal": "whatsapp", "telefone": "912345678", "agente": A5, "conversa_id": "conv-1"}
INQ_ESCRITURA = {"id": "inq-1", "tipo": "escritura_vendedor", "primeiro_nome": "Ana", "consultor": "Joana"}
INQ_RESCISAO = {"id": "inq-2", "tipo": "rescisao_vendedor", "primeiro_nome": "Rui", "consultor": "Joana"}


# ── registo ───────────────────────────────────────────────────

def test_a5_so_tem_as_tools_do_inquerito():
    assert ASSISTENTES[A5]["tools"] == ["registar_satisfacao", "registar_testemunho"]
    nomes = [t["name"] for t in tools.tools_para(ASSISTENTES[A5]["tools"])]
    assert nomes == ["registar_satisfacao", "registar_testemunho"]


# ── encaminhamento ────────────────────────────────────────────

def test_inquerito_aberto_ganha_a_lead_antiga(monkeypatch):
    async def _inq(tel):
        return INQ_ESCRITURA

    async def _lead(tel):
        return {"tipo": "compra"}

    monkeypatch.setattr(guards, "satisfacao_aberta", _inq)
    monkeypatch.setattr(guards, "lead_aberta", _lead)
    assert asyncio.run(guards.agente_de_lead("912345678")) == A5


def test_sem_inquerito_mantem_o_encaminhamento(monkeypatch):
    async def _nada(tel):
        return None

    async def _lead(tel):
        return {"tipo": "compra"}

    monkeypatch.setattr(guards, "satisfacao_aberta", _nada)
    monkeypatch.setattr(guards, "lead_aberta", _lead)
    assert asyncio.run(guards.agente_de_lead("912345678")) == "a1_vendedor"


def test_falha_a_ler_o_inquerito_nao_parte_o_encaminhamento(monkeypatch):
    class _SB:
        def rpc(self, *a, **k):
            raise RuntimeError("rede")

    monkeypatch.setattr(guards, "get_supabase", lambda: _SB())
    assert asyncio.run(guards.satisfacao_aberta("912345678")) is None


# ── registar_satisfacao ───────────────────────────────────────

@pytest.fixture
def registo(monkeypatch):
    r = {"rpc": [], "tarefas": [], "avisos": [], "inq": INQ_ESCRITURA, "passo": {}}

    def _rpc(fn, params):
        r["rpc"].append((fn, params))
        return r["passo"] if fn == "fn_satisf_registar" else None

    monkeypatch.setattr(tools, "_satisfacao_aberta", lambda tel: r["inq"])
    monkeypatch.setattr(tools, "_rpc", _rpc)
    monkeypatch.setattr(tools, "_inserir_tarefa", r["tarefas"].append)
    monkeypatch.setattr(tools, "notificar", lambda assunto, corpo, imovel_ref=None: r["avisos"].append((assunto, corpo)))
    return r


def test_nota_baixa_escala_uma_vez_e_nao_manda_links(registo):
    registo["passo"] = {"escalar": True, "tipo": "escritura_vendedor", "nps": 4}
    resp = asyncio.run(tools._registar_satisfacao({"nps": 4, "motivo": "demorou muito"}, CONTEXTO))

    assert len(registo["tarefas"]) == 1
    t = registo["tarefas"][0]
    assert t["tipo"] == "escalar" and t["agente"] == A5 and t["motivo"] == "satisfação — nota baixa"
    assert "4/10" in t["descricao"] and "demorou muito" in t["descricao"]
    assert len(registo["avisos"]) == 1
    assert ("fn_satisf_marcar_escalado", {"p_id": "inq-1"}) in registo["rpc"]
    assert "http" not in resp and "direção" in resp


def test_nota_baixa_ja_escalada_nao_repete(registo):
    registo["passo"] = {"escalar": False, "tipo": "escritura_vendedor", "nps": 4}
    resp = asyncio.run(tools._registar_satisfacao({"nps": 4}, CONTEXTO))
    assert registo["tarefas"] == [] and registo["avisos"] == []
    assert "http" not in resp


def test_nota_alta_recebe_os_links_do_servidor(registo):
    registo["passo"] = {"tipo": "escritura_vendedor", "nps": 10,
                        "google_link": "https://portal.exemplo/avaliar?t=abc",
                        "testemunho_link": "https://portal.exemplo/testemunho?t=abc",
                        "resumo_link": "https://portal.exemplo/testemunho?t=abc"}
    resp = asyncio.run(tools._registar_satisfacao({"nps": 10, "nota_consultor": 5}, CONTEXTO))

    assert "https://portal.exemplo/avaliar?t=abc" in resp
    assert "https://portal.exemplo/testemunho?t=abc" in resp
    assert registo["tarefas"] == []
    fn, params = [x for x in registo["rpc"] if x[0] == "fn_satisf_registar"][0]
    assert params == {"p_id": "inq-1", "p": {"nps": 10, "nota_consultor": 5}}


def test_sem_nota_pede_a_nota(registo):
    registo["passo"] = {"falta": "nps"}
    resp = asyncio.run(tools._registar_satisfacao({"motivo": "correu bem"}, CONTEXTO))
    assert "0 a 10" in resp and registo["tarefas"] == []


def test_rescisao_escala_e_despede(registo):
    registo["inq"] = INQ_RESCISAO
    registo["passo"] = {"escalar": True, "tipo": "rescisao_vendedor"}
    resp = asyncio.run(tools._registar_satisfacao({"motivo": "poucas visitas", "voltaria": "talvez"}, CONTEXTO))
    assert registo["tarefas"][0]["motivo"] == "satisfação — rescisão"
    assert "talvez" in registo["tarefas"][0]["descricao"]
    assert "http" not in resp and "despede" in resp


def test_sem_inquerito_nao_grava(registo):
    registo["inq"] = None
    resp = asyncio.run(tools._registar_satisfacao({"nps": 9}, CONTEXTO))
    assert registo["rpc"] == [] and "Não há inquérito" in resp


# ── registar_testemunho ───────────────────────────────────────

def test_testemunho_grava_texto_e_autorizacao(registo):
    asyncio.run(tools._registar_testemunho(
        {"texto": " Correu tudo bem. ", "autoriza_publicar": True, "nome_a_publicar": "Ana R."}, CONTEXTO))
    assert ("fn_satisf_testemunho", {"p_id": "inq-1", "p_texto": "Correu tudo bem.", "p_autoriza": True,
                                     "p_nome": "Ana R."}) in registo["rpc"]


def test_rescisao_nao_grava_testemunho(registo):
    registo["inq"] = INQ_RESCISAO
    asyncio.run(tools._registar_testemunho({"texto": "x", "autoriza_publicar": True}, CONTEXTO))
    assert registo["rpc"] == []


# ── envio ─────────────────────────────────────────────────────

def test_texto_do_template():
    assert satisfacao.texto_do_template("Olá {{1}}! Fala a Sofia.", "Ana") == "Olá Ana! Fala a Sofia."


@pytest.fixture
def envio(monkeypatch):
    r = {"fila": [], "marcas": [], "templates": [], "conversas": []}

    def _rpc(fn, params):
        if fn == "fn_satisf_para_enviar":
            return r["fila"]
        r["marcas"].append(params)

    async def _tpl(to, nome, lingua, parametros, phone_number_id=None):
        r["templates"].append((to, nome, lingua, parametros))
        return True, "wamid.1"

    async def _save(conversa_id, canal, participante, mensagens, agente=None):
        r["conversas"].append((participante, mensagens, agente))
        return "conv-x"

    monkeypatch.setattr(satisfacao, "_rpc", _rpc)
    monkeypatch.setattr(meta_api, "send_template", _tpl)
    monkeypatch.setattr(satisfacao, "save_conversation", _save)
    return r


TPL = {"nome": "satisfacao_vendedor", "lingua": "pt_PT", "texto": "Olá {{1}}! Fala a Sofia."}


def test_envio_manda_template_e_semeia_a_conversa(envio):
    envio["fila"] = [{"id": "i1", "telefone": "912345678", "primeiro_nome": "Ana", "template": TPL}]
    out = asyncio.run(satisfacao.enviar_inqueritos())

    assert out == {"na_fila": 1, "enviados": 1, "erros": 0}
    assert envio["templates"] == [("351912345678", "satisfacao_vendedor", "pt_PT", ["Ana"])]
    participante, mensagens, agente = envio["conversas"][0]
    assert participante == "351912345678" and agente == A5
    assert mensagens[0]["role"] == "assistant" and mensagens[0]["content"] == "Olá Ana! Fala a Sofia."
    assert envio["marcas"] == [{"p_id": "i1", "p_ok": True, "p_erro": None, "p_texto": "Olá Ana! Fala a Sofia."}]


def test_envio_recusa_numero_que_nao_e_telemovel_portugues(envio):
    envio["fila"] = [{"id": "i2", "telefone": "233123456", "primeiro_nome": "Ana", "template": TPL}]
    out = asyncio.run(satisfacao.enviar_inqueritos())
    assert out["erros"] == 1 and envio["templates"] == []
    assert envio["marcas"][0]["p_ok"] is False


def test_envio_sem_nome_nao_sai(envio):
    envio["fila"] = [{"id": "i3", "telefone": "912345678", "primeiro_nome": "", "template": TPL}]
    asyncio.run(satisfacao.enviar_inqueritos())
    assert envio["templates"] == [] and envio["marcas"][0]["p_ok"] is False


def test_payload_do_template(monkeypatch):
    enviados = []

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {"messages": [{"id": "wamid.9"}]}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            enviados.append(json)
            return _Resp()

    monkeypatch.setattr(meta_api.httpx, "AsyncClient", _Client)
    ok, detalhe = asyncio.run(meta_api.send_template("351912345678", "satisfacao_comprador", "pt_PT", ["Ana"]))
    assert ok and detalhe == "wamid.9"
    t = enviados[0]["template"]
    assert enviados[0]["type"] == "template" and t["name"] == "satisfacao_comprador"
    assert t["language"] == {"code": "pt_PT"}
    assert t["components"][0]["parameters"] == [{"type": "text", "text": "Ana"}]


# ── contexto ──────────────────────────────────────────────────

def _contexto_com(monkeypatch, inq):
    async def _inq(tel):
        return inq

    class _SB:
        def rpc(self, *a, **k):
            class _Q:
                def execute(self):
                    return None
            return _Q()

    monkeypatch.setattr(engine, "satisfacao_aberta", _inq)
    monkeypatch.setattr(engine, "get_supabase", lambda: _SB())


def test_contexto_injecta_o_template_so_na_thread_nova_antes_de_responder(monkeypatch):
    inq = {**INQ_ESCRITURA, "template_texto": "Olá Ana! Fala a Sofia.", "respondeu_em": None}
    _contexto_com(monkeypatch, inq)
    perfil, template, lead = asyncio.run(engine._contexto_satisfacao("912345678", "", thread_nova=True))
    assert template["role"] == "assistant" and template["content"] == "Olá Ana! Fala a Sofia."
    assert lead is None and "VENDEDOR" in perfil and "Joana" in perfil

    _, template, _ = asyncio.run(engine._contexto_satisfacao("912345678", "", thread_nova=False))
    assert template is None


def test_contexto_nao_repete_a_nota_ja_dada(monkeypatch):
    inq = {**INQ_ESCRITURA, "nps": 9, "template_texto": "x", "respondeu_em": "2026-10-21T10:00:00Z"}
    _contexto_com(monkeypatch, inq)
    perfil, template, _ = asyncio.run(engine._contexto_satisfacao("912345678", "", thread_nova=True))
    assert "9/10" in perfil and template is None
