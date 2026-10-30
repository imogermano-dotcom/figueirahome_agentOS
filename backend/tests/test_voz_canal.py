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
from app.agents.voice.claude_agent import FIM_CHAMADA, _CORPO_SAUDACAO  # noqa: E402
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
    assert _CORPO_SAUDACAO in p and FIM_CHAMADA in p and "Estás numa chamada telefónica" in p
    assert "mesmo número" in p, "telefone conhecido: pergunta só se o consultor pode ligar para esse número"
    assert "Este contacto vem do WhatsApp" not in p


def test_prompt_de_voz_proibe_frases_de_espera_e_novo_cumprimento():
    """Chamada de 27/10: «Fico a registar o orçamento, João, um momento» e a pessoa desligou à espera; e «Olá João» logo a seguir à saudação."""
    p = _prompt("voz", "912345678")
    assert "um momento" in p and "bastar-se a si própria" in p and "sem «olá»" in p


def test_prompt_de_voz_sem_numero_pede_o_numero_inteiro():
    assert "nove dígitos" in _prompt("voz", None) and "mesmo número" not in _prompt("voz", None)


def test_outros_canais_nao_levam_a_instrucao_de_voz():
    for canal in ("whatsapp", "site", "web"):
        assert "Estás numa chamada telefónica" not in _prompt(canal)


def test_voz_tem_limite_de_tokens_curto():
    assert assistants.MAX_TOKENS["voz"] <= 400


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


def _turno(*args, **kw):
    """Um turno inteiro: a resposta e o que ficou por fazer a seguir (gravação, lead), no mesmo ciclo de eventos."""
    async def _c():
        r = await engine.responder(*args, **kw)
        await engine.esperar_diferidos()
        return r

    return asyncio.run(_c())


def test_turno_de_voz_usa_o_telefone_da_chamada_e_so_ferramentas_de_registo(motor):
    r = _turno("voz", "call-1", "Quero comprar uma casa", telefone="+351912345678")
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
        _turno("voz", "call-1", "olá", agente=assistants.A2, telefone="912345678")
    assert motor["config"] == 1 and motor["perfil"] == 1
    _turno("voz", "call-2", "olá", agente=assistants.A2, telefone="912345678")
    assert motor["config"] == 2, "outra chamada, outra leitura"
    engine.descartar_cache_voz("call-1")
    assert "call-1" not in engine._cache_voz


def test_whatsapp_continua_a_ler_tudo_em_cada_turno(motor):
    for _ in range(2):
        asyncio.run(engine.responder("whatsapp", "351912345678", "olá", agente=assistants.A2))
    assert motor["config"] == 2 and motor["perfil"] == 2


def test_chamada_sem_numero_nao_procura_perfil(motor):
    _turno("voz", "call-1", "olá", agente=assistants.A2, telefone="desconhecido")
    assert motor["perfil"] == 0


# ── o fim do turno depois da resposta ─────────────────────────────────────

def _resposta_com_tool(texto, nome="guardar_dados_cliente"):
    blocos = ([{"type": "text", "text": texto}] if texto else []) + [
        {"type": "tool_use", "id": "t1", "name": nome, "input": {"nome": "Ana"}}]
    return {"stop_reason": "tool_use", "usage": {}, "content": blocos}


def _preparar(monkeypatch, motor, respostas):
    """Respostas do modelo em fila; regista a ordem de tudo o que acontece."""
    ordem = []
    fila = list(respostas)

    class _R:
        def __init__(self, d):
            self.d = d

        def raise_for_status(self):
            pass

        def json(self):
            return self.d

    class _C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            ordem.append("modelo")
            return _R(fila.pop(0))

    async def _tool(nome, entrada, contexto):
        ordem.append("tool:" + nome)
        return "Registado."

    original = engine.save_conversation

    async def _gravar(*a, **k):
        ordem.append("gravar")
        return await original(*a, **k)

    monkeypatch.setattr(engine.httpx, "AsyncClient", _C)
    monkeypatch.setattr(engine, "execute_tool", _tool)
    monkeypatch.setattr(engine, "save_conversation", _gravar)
    return ordem


def test_frase_com_ferramenta_de_registo_sai_logo_e_o_registo_corre_a_seguir(monkeypatch, motor):
    ordem = _preparar(monkeypatch, motor, [_resposta_com_tool("Obrigada, Ana. Um consultor entra em contacto.")])

    async def _c():
        r = await engine.responder("voz", "call-1", "sou a Ana", agente=assistants.A2, telefone="912345678")
        antes = list(ordem)
        await engine.esperar_diferidos()
        return r, antes

    r, antes = asyncio.run(_c())
    assert r == "Obrigada, Ana. Um consultor entra em contacto."
    assert antes == ["modelo"], "a resposta sai antes de qualquer ferramenta ou gravação"
    assert ordem == ["modelo", "tool:guardar_dados_cliente", "gravar"], "o registo antes da gravação do turno"
    assert motor["gravado"][0][2][-1] == r


def test_sem_frase_escrita_volta_ao_caminho_normal(monkeypatch, motor):
    texto = {"stop_reason": "end_turn", "usage": {}, "content": [{"type": "text", "text": "Registado, até breve."}]}
    ordem = _preparar(monkeypatch, motor, [_resposta_com_tool(""), texto])
    assert _turno("voz", "call-1", "sou a Ana", agente=assistants.A2, telefone="912345678") == "Registado, até breve."
    assert ordem[:3] == ["modelo", "tool:guardar_dados_cliente", "modelo"], "ferramenta antes da 2.ª chamada, como antes"


def test_pedir_visita_nunca_e_adiada_porque_pode_recusar(monkeypatch, motor):
    texto = {"stop_reason": "end_turn", "usage": {}, "content": [{"type": "text", "text": "Não consegui registar."}]}
    ordem = _preparar(monkeypatch, motor, [_resposta_com_tool("Vou registar a visita.", "pedir_visita"), texto])
    assert _turno("voz", "call-1", "quero visitar", agente=assistants.A1, telefone="912345678") == "Não consegui registar."
    assert ordem[:3] == ["modelo", "tool:pedir_visita", "modelo"]


def test_o_turno_seguinte_espera_pelo_fim_do_anterior(monkeypatch, motor):
    ordem = _preparar(monkeypatch, motor, [_resposta_com_tool("Anotado."), {
        "stop_reason": "end_turn", "usage": {}, "content": [{"type": "text", "text": "Diga."}]}])

    async def _c():
        await engine.responder("voz", "call-1", "um", agente=assistants.A2, telefone="912345678")
        await engine.responder("voz", "call-1", "dois", agente=assistants.A2, telefone="912345678")
        await engine.esperar_diferidos()

    asyncio.run(_c())
    assert ordem.index("gravar") < len(ordem) - 1 and ordem[:3] == ["modelo", "tool:guardar_dados_cliente", "gravar"]
    assert ordem[3] == "modelo", "o 2.º turno só começa depois de o 1.º gravar"


def test_ferramenta_que_falha_nao_prende_a_conversa(monkeypatch, motor):
    _preparar(monkeypatch, motor, [_resposta_com_tool("Anotado."), {
        "stop_reason": "end_turn", "usage": {}, "content": [{"type": "text", "text": "Diga."}]}])

    async def _rebenta(*a, **k):
        raise RuntimeError("base em baixo")

    monkeypatch.setattr(engine, "execute_tool", _rebenta)

    async def _c():
        await engine.responder("voz", "call-1", "um", agente=assistants.A2, telefone="912345678")
        await engine.esperar_diferidos()
        return await asyncio.wait_for(
            engine.responder("voz", "call-1", "dois", agente=assistants.A2, telefone="912345678"), 5)

    assert asyncio.run(_c()) == "Diga."


def test_outros_canais_continuam_a_executar_as_ferramentas_antes_de_responder(monkeypatch, motor):
    texto = {"stop_reason": "end_turn", "usage": {}, "content": [{"type": "text", "text": "Feito."}]}
    ordem = _preparar(monkeypatch, motor, [_resposta_com_tool("Anotado."), texto])
    r = asyncio.run(engine.responder("whatsapp", "351912345678", "olá", agente=assistants.A2))
    # conversa nova: a linha grava-se logo (para as ferramentas lhe ligarem as tarefas) e regrava-se no fim
    assert r == "Feito." and ordem == ["gravar", "modelo", "tool:guardar_dados_cliente", "modelo", "gravar"]


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


def test_conversa_nova_de_whatsapp_e_gravada_antes_do_modelo_e_a_de_voz_nao(motor, monkeypatch):
    """29/10: a tarefa `escalar` do 1.º turno ficou sem `conversa_id` e o nudge incomodou quem já esperava chamada."""
    ordem = []
    original = engine.save_conversation

    async def _marca(conversa_id, canal, participante, mensagens, agente):
        ordem.append((canal, len(motor["payloads"])))  # quantas chamadas ao modelo já houve
        return await original(conversa_id, canal, participante, mensagens, agente)

    monkeypatch.setattr(engine, "save_conversation", _marca)
    _turno("whatsapp", "351912345678", "Podem ligar-me?", agente=assistants.A1)
    assert ordem[0] == ("whatsapp", 0), "a linha da conversa existe antes de qualquer ferramenta"
    ordem.clear()
    antes = len(motor["payloads"])
    _turno("voz", "call-9", "olá", agente=assistants.A2, telefone="912345678")
    assert ordem[0] == ("voz", antes + 1), "na voz a gravação continua a seguir à resposta"
