"""Voz: o telefone é o da chamada, não o que o STT ouviu (`claude_agent.instrucao_telefone`, `save_call.telefone_da_chamada`).

Corre com `pytest backend/tests/` ou `python backend/tests/test_voz_telefone.py`. Sem rede nem credenciais.
Caso real de 17/10: a assistente pedia o telefone dígito a dígito («qual é o dígito que falta no final?») a quem tinha dito
sete dos nove, e o número gravado seria o truncado.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.voice import claude_agent, save_call  # noqa: E402


@pytest.mark.parametrize("origem", ["+351912345678", "00351912345678", "912345678", "351912345678"])
def test_com_numero_da_chamada_a_assistente_nao_o_pede(origem):
    t = claude_agent.instrucao_telefone(origem)
    assert "já é conhecido" in t and "nunca o peças" in t
    assert "um dígito isolado" in t, "e nunca pede dígitos soltos"


@pytest.mark.parametrize("origem", [None, "", "anonymous", "desconhecido", "12345"])
def test_chamada_anonima_pede_o_numero_completo_de_uma_vez(origem):
    t = claude_agent.instrucao_telefone(origem)
    assert "não mostra o número" in t and "de uma só vez" in t
    assert "nunca peças um dígito isolado" in t


def test_o_prompt_base_ja_nao_manda_pedir_digito_a_digito():
    assert "dígito a dígito" not in claude_agent._SYSTEM_BASE
    assert "Número de telefone de contacto" not in claude_agent._SYSTEM_BASE


def test_numero_dito_truncado_nao_substitui_o_da_chamada():
    assert save_call.telefone_da_chamada("9159025", "+351912345678") == "+351912345678"
    assert save_call.telefone_da_chamada(None, "+351912345678") == "+351912345678"
    assert save_call.telefone_da_chamada("", "+351912345678") == "+351912345678"


def test_numero_dito_completo_e_diferente_substitui_o_da_chamada():
    assert save_call.telefone_da_chamada("933 444 555", "+351912345678") == "933 444 555"


def test_numero_dito_igual_ao_da_chamada_fica_o_da_chamada():
    assert save_call.telefone_da_chamada("912 345 678", "+351912345678") == "+351912345678"


def test_sem_numero_da_chamada_usa_o_dito_se_completo():
    assert save_call.telefone_da_chamada("912345678", None) == "912345678"
    assert save_call.telefone_da_chamada("9159025", None) is None


def test_pergunta_do_telefone_e_se_o_consultor_pode_ligar():
    # 19/10: «Pode ligar para o número de onde está a chamar?» perguntava ao contrário.
    t = claude_agent.instrucao_telefone("+351912345678")
    assert "Um consultor pode ligar-lhe para este mesmo número?" in t


def test_despedida_marca_o_fim_e_a_marca_nao_e_falada(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from app.agents.voice.session import CallSession

    async def cria(**_):
        return SimpleNamespace(content=[SimpleNamespace(text="Muito obrigada, João! Até breve! FIM_CHAMADA")])

    monkeypatch.setattr(claude_agent._client.messages, "create", cria)
    s = CallSession("x", "+351912345678", system_prompt="p")
    texto = asyncio.run(claude_agent.get_response(s, "sim, pode"))
    assert s.terminar and "FIM_CHAMADA" not in texto and texto.endswith("Até breve!")
    assert "FIM_CHAMADA" not in s.historico[-1]["content"]


def test_resposta_normal_nao_termina_a_chamada(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from app.agents.voice.session import CallSession

    async def cria(**_):
        return SimpleNamespace(content=[SimpleNamespace(text="Qual é o seu orçamento?")])

    monkeypatch.setattr(claude_agent._client.messages, "create", cria)
    s = CallSession("x", "+351912345678", system_prompt="p")
    asyncio.run(claude_agent.get_response(s, "olá"))
    assert not s.terminar


def test_voz_do_speak_vem_da_configuracao(monkeypatch):
    import asyncio
    from app.agents.voice import telnyx_api
    from app.config import settings

    enviados = []

    class R:
        status_code = 200

    class C:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None):
            enviados.append(json)
            return R()

    monkeypatch.setattr(telnyx_api.httpx, "AsyncClient", C)
    monkeypatch.setattr(telnyx_api, "_headers", lambda: {})
    assert settings.voz_tts == "Polly.Ines-Neural"  # por omissão não muda a voz
    monkeypatch.setattr(settings, "voz_tts", "Azure.pt-PT-RaquelNeural")
    asyncio.run(telnyx_api.speak("cc", "Olá"))
    assert enviados[0]["voice"] == "Azure.pt-PT-RaquelNeural" and enviados[0]["language"] == "pt-PT"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
