"""Voz como canal do motor (`docs/fases/voz-como-canal-plano.md`, pedido #25, fase 1).

A chamada passa a correr no motor dos assistentes: instrução de canal, só ferramentas de registo, telefone da chamada
no contexto, sem template nem apresentação, e o perfil lido uma vez por chamada. Sem rede.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker import assistants, engine, tools  # noqa: E402
from app.agents.voice import audio_ws  # noqa: E402
from app.agents.voice.claude_agent import FIM_CHAMADA, SAUDACAO  # noqa: E402
from app.agents.voice.session import CallSession  # noqa: E402

REGISTO = {"guardar_dados_cliente", "pedir_visita", "escalar_para_humano", "encerrar_lead"}


def _nomes(ds):
    return {d["name"] for d in ds}


# ── ferramentas por canal ─────────────────────────────────────────────────

def test_voz_so_recebe_ferramentas_de_registo():
    for chave in (assistants.A1, assistants.A2, assistants.A3, assistants.A4):
        assert _nomes(tools.tools_para(assistants.ASSISTENTES[chave]["tools"], "voz")) <= REGISTO


def test_voz_nunca_tem_pesquisa_nem_consultas_do_broker():
    nomes = _nomes(tools.tools_para(assistants.ASSISTENTES[assistants.A1]["tools"], "voz"))
    assert not nomes & {"pesquisar_imoveis", "ficha_imovel", "link_imovel"}
    assert tools.tools_para(assistants.ASSISTENTES[assistants.BROKER]["tools"], "voz") == []


def test_outros_canais_ficam_como_estavam():
    a1 = assistants.ASSISTENTES[assistants.A1]["tools"]
    assert _nomes(tools.tools_para(a1)) == set(a1) == _nomes(tools.tools_para(a1, "whatsapp"))


# ── o prompt ──────────────────────────────────────────────────────────────

def _prompt(canal, telefone=None):
    return engine._montar_system_prompt(assistants.ASSISTENTES[assistants.A1], "", "", canal, telefone=telefone)


def test_prompt_de_voz_tem_a_instrucao_de_canal_e_a_saudacao():
    p = _prompt("voz", "912345678")
    assert SAUDACAO in p and FIM_CHAMADA in p and "Estás numa chamada telefónica" in p
    assert "mesmo número" in p, "telefone conhecido: pergunta só se o consultor pode ligar para esse número"
    assert "Este contacto vem do WhatsApp" not in p


def test_prompt_de_voz_sem_numero_pede_o_numero_inteiro():
    assert "nove dígitos" in _prompt("voz", None) and "mesmo número" not in _prompt("voz", None)


def test_outros_canais_nao_levam_a_instrucao_de_voz():
    for canal in ("whatsapp", "site", "web"):
        assert "Estás numa chamada telefónica" not in _prompt(canal)


def test_voz_tem_limite_de_tokens_curto():
    assert assistants.MAX_TOKENS["voz"] <= 256


def test_voz_nao_prefixa_a_apresentacao_da_matilde():
    r = "Que tipo de imóvel procura?"
    assert engine._garantir_apresentacao(r, assistants.A1, True, [], "voz") == r
    assert engine._garantir_apresentacao(r, assistants.A1, True, [], "whatsapp") != r


# ── um turno no motor ─────────────────────────────────────────────────────

@pytest.fixture
def motor(monkeypatch):
    visto = {"payloads": [], "contexto": [], "config": 0, "perfil": 0, "gravado": []}

    async def _carregar(canal, participante):
        return None, [], None

    async def _config(agente):
        visto["config"] += 1
        return "", True

    async def _contexto(telefone, thread_nova, agente=None):
        visto["perfil"] += 1
        visto["contexto"].append((telefone, thread_nova))
        return "", {"role": "assistant", "content": "template de WhatsApp"}, None

    async def _vazio(*a, **k):
        return []

    async def _gravar(conversa_id, canal, participante, mensagens, agente):
        visto["gravado"].append((canal, participante, [m["content"] for m in mensagens]))
        return "c1"

    async def _nada(*a, **k):
        return None

    class _Resposta:
        def raise_for_status(self):
            pass

        def json(self):
            return {"stop_reason": "end_turn", "usage": {}, "content": [{"type": "text", "text": "Boa tarde, diga-me o seu nome."}]}

    class _Cliente:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            visto["payloads"].append(json)
            return _Resposta()

    monkeypatch.setattr(engine, "load_conversation", _carregar)
    monkeypatch.setattr(engine, "load_config", _config)
    monkeypatch.setattr(engine, "_contexto_inicial", _contexto)
    monkeypatch.setattr(engine, "motivos_escalados", _vazio)
    monkeypatch.setattr(engine, "tools_ja_usadas", _vazio)
    monkeypatch.setattr(engine, "save_conversation", _gravar)
    monkeypatch.setattr(engine, "_registar_interacao", _nada)
    monkeypatch.setattr(engine, "promover_se_qualificada", _nada)
    monkeypatch.setattr(engine.httpx, "AsyncClient", _Cliente)
    engine._cache_voz.clear()
    engine._locks.clear()
    return visto


def test_turno_de_voz_usa_o_telefone_da_chamada_e_so_ferramentas_de_registo(motor):
    r = asyncio.run(engine.responder("voz", "call-1", "Quero comprar uma casa", telefone="+351912345678"))
    assert r == "Boa tarde, diga-me o seu nome."
    p = motor["payloads"][0]
    assert p["max_tokens"] == assistants.MAX_TOKENS["voz"]
    assert {t["name"] for t in p["tools"]} <= REGISTO
    assert "tool_choice" not in p, "a pesquisa forçada da Matilde não existe na voz"
    assert "Estás numa chamada telefónica" in p["system"][0]["text"]
    assert motor["contexto"] == [("912345678", False)], "perfil pelo número da chamada, sem tratar como thread nova (sem template)"
    assert motor["gravado"][0][:2] == ("voz", "call-1")
    assert "template de WhatsApp" not in motor["gravado"][0][2]


def test_perfil_e_configuracao_lidos_uma_vez_por_chamada(motor):
    for _ in range(3):
        asyncio.run(engine.responder("voz", "call-1", "olá", agente=assistants.A2, telefone="912345678"))
    assert motor["config"] == 1 and motor["perfil"] == 1
    asyncio.run(engine.responder("voz", "call-2", "olá", agente=assistants.A2, telefone="912345678"))
    assert motor["config"] == 2, "outra chamada, outra leitura"
    engine.descartar_cache_voz("call-1")
    assert "call-1" not in engine._cache_voz


def test_whatsapp_continua_a_ler_tudo_em_cada_turno(motor):
    for _ in range(2):
        asyncio.run(engine.responder("whatsapp", "351912345678", "olá", agente=assistants.A2))
    assert motor["config"] == 2 and motor["perfil"] == 2


def test_chamada_sem_numero_nao_procura_perfil(motor):
    asyncio.run(engine.responder("voz", "call-1", "olá", agente=assistants.A2, telefone="desconhecido"))
    assert motor["perfil"] == 0


# ── a ponte da voz ────────────────────────────────────────────────────────

def _sessao():
    return CallSession(call_control_id="call-1", numero_origem="+351912345678")


def _motor_responde(monkeypatch, texto):
    visto = {}

    async def _r(canal, participante, mensagem, agente=None, telefone=None):
        visto.update(canal=canal, participante=participante, mensagem=mensagem, telefone=telefone)
        return texto

    monkeypatch.setattr(engine, "responder", _r)
    return visto


def test_ponte_passa_a_chamada_e_o_numero_ao_motor(monkeypatch):
    visto = _motor_responde(monkeypatch, "Diga-me o seu nome.")
    assert asyncio.run(audio_ws.resposta_do_motor(_sessao(), "quero comprar")) == "Diga-me o seu nome."
    assert visto == {"canal": "voz", "participante": "call-1", "mensagem": "quero comprar", "telefone": "+351912345678"}


def test_ponte_desliga_na_despedida_e_nao_fala_a_marca():
    s = _sessao()
    r = asyncio.run(_com_motor("Até breve! " + FIM_CHAMADA, s))
    assert s.terminar is True and FIM_CHAMADA not in r and "Até breve" in r


def test_ponte_limpa_markdown_e_retos():
    r = asyncio.run(_com_motor("**Perfeito** [A usar tool x] senhor Silva", _sessao()))
    assert "*" not in r and "[" not in r and "Perfeito" in r


@pytest.mark.parametrize("texto", ["", "Ocorreu um erro. Tenta novamente."])
def test_ponte_pede_para_repetir_em_vez_de_dizer_o_erro(texto):
    r = asyncio.run(_com_motor(texto, _sessao()))
    assert "repetir" in r and "erro" not in r.lower()


async def _com_motor(texto, sessao):
    async def _r(*a, **k):
        return texto

    original = engine.responder
    engine.responder = _r
    try:
        return await audio_ws.resposta_do_motor(sessao, "x")
    finally:
        engine.responder = original


# ── o interruptor ─────────────────────────────────────────────────────────

def test_interruptor_vem_desligado():
    from app.config import Settings

    assert Settings(_env_file=None).voz_como_canal is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
