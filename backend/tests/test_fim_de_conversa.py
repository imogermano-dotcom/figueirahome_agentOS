"""Fim de conversa no WhatsApp: a assistente já se despediu e a pessoa só responde com emojis, «obrigado» ou «até logo».

Caso real de 22/10: uma lead trocou ~40 mensagens de carinhas e «tchau» com a Matilde e o modelo respondeu a todas.
Sem rede. Corre com `pytest backend/tests/` ou `python backend/tests/test_fim_de_conversa.py`.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.broker import engine, guards  # noqa: E402
from app.agents.broker.channels.whatsapp import webhook  # noqa: E402


def test_despedida_da_assistente_inclui_emoji_sozinho_e_saudacoes():
    for ok in ("Boa sorte na procura. 😊", "Até breve! 😊", "😄", "👋", "Bom fim de semana 😊", "Disponha! 👋"):
        assert guards.e_despedida(ok), ok
    for nao in ("Qual o orçamento que tem disponível?", "Aqui está a ficha do imóvel:", "", None):
        assert not guards.e_despedida(nao), nao


def test_fecho_da_pessoa_so_quando_nao_pede_nada():
    for ok in ("😎", "🤚🏻", "Obrigado", "Obrigada!", "Até logo", "Tchau", "Chao", "Ok", "Boa noite", "😹 😹"):
        assert guards.e_fecho_da_pessoa(ok), ok
    for nao in ("Quero comprar", "Obrigado, mas e o preço?", "Sim", "Qual o piso?", "Já lê disse que me estou a cuidar de mim", "", None):
        assert not guards.e_fecho_da_pessoa(nao), nao


def test_recusa_curta_e_sem_pergunta():
    for ok in ("Não estou interessada", "Não tenho interesse, obrigado", "Já não preciso", "Sem interesse", "Não me contacte mais"):
        assert guards.e_recusa(ok), ok
    for nao in ("Estou interessado", "Não sei", "Não tenho interesse em arrendar? Quero comprar", "Quanto custa?", "", None):
        assert not guards.e_recusa(nao), nao


def _motor(monkeypatch, mensagens, chamadas):
    async def _carregar(canal, participante):
        return "c1", list(mensagens), "a1_vendedor"

    async def _nao_devia(*a, **k):
        chamadas.append(a)
        raise AssertionError("não devia chegar ao modelo")

    monkeypatch.setattr(engine, "load_conversation", _carregar)
    monkeypatch.setattr(engine, "load_config", _nao_devia)


def _conversa(ultima):
    return [{"role": "user", "content": "Quero saber mais"}, {"role": "assistant", "content": ultima}]


def test_motor_nao_responde_a_emoji_depois_da_despedida(monkeypatch):
    chamadas = []
    _motor(monkeypatch, _conversa("Boa sorte na procura. 😊"), chamadas)
    assert asyncio.run(engine._responder_sem_lock("whatsapp", "351900000001", "🤪")) == ""
    assert chamadas == []


def test_motor_nao_responde_a_obrigado_depois_da_despedida(monkeypatch):
    chamadas = []
    _motor(monkeypatch, _conversa("Já está entregue ao consultor! Bom fim de semana 😊"), chamadas)
    assert asyncio.run(engine._responder_sem_lock("whatsapp", "351900000001", "Obrigado")) == ""


def test_motor_responde_se_a_pessoa_pergunta_depois_da_despedida(monkeypatch):
    """A despedida não cala quem volta com um pedido a sério: segue para o modelo (aqui o duplo rebenta de propósito)."""
    chamadas = []
    _motor(monkeypatch, _conversa("Boa sorte na procura. 😊"), chamadas)
    with pytest.raises(AssertionError):
        asyncio.run(engine._responder_sem_lock("whatsapp", "351900000001", "Afinal quero ver o imóvel"))
    assert chamadas, "chegou à configuração do assistente"


def test_motor_responde_a_emoji_se_a_assistente_nao_se_despediu(monkeypatch):
    chamadas = []
    _motor(monkeypatch, _conversa("Qual o orçamento que tem disponível?"), chamadas)
    with pytest.raises(AssertionError):
        asyncio.run(engine._responder_sem_lock("whatsapp", "351900000001", "👍"))
    assert chamadas


def test_canal_site_nunca_fica_calado(monkeypatch):
    chamadas = []
    _motor(monkeypatch, _conversa("Boa sorte na procura. 😊"), chamadas)
    with pytest.raises(AssertionError):
        asyncio.run(engine._responder_sem_lock("site", "visitante1", "🤪"))


def test_webhook_nao_envia_resposta_vazia(monkeypatch):
    enviadas = []

    async def _responder(**k):
        return ""

    async def _enviar(*a, **k):
        enviadas.append(a)

    async def _ler(*a, **k):
        return None

    async def _agente(*a, **k):
        return None

    monkeypatch.setattr(webhook, "_ja_processada", lambda _id: False)
    monkeypatch.setattr(webhook, "mark_as_read", _ler)
    monkeypatch.setattr(webhook, "agente_de_lead", _agente)
    monkeypatch.setattr(webhook, "responder", _responder)
    monkeypatch.setattr(webhook, "send_text_message", _enviar)
    asyncio.run(webhook._handle_message("351900000001", "wamid.X", "🤪"))
    assert enviadas == []


def test_nudge_nao_insiste_depois_de_uma_recusa(monkeypatch):
    from tests.test_nudge import _conversa as conversa_nudge, _montar
    from app.agents.broker import nudge

    conversa = conversa_nudge("c1", "351900000001", ultimo_texto="Tudo bem, desejo-lhe uma boa semana de trabalho.")
    conversa["mensagens"][0]["content"] = "Não estou interessada, obrigado"
    estado = _montar(monkeypatch, [conversa], {"351900000001": {"estado": "contactada", "contacto_humano_em": None}})
    resumo = asyncio.run(nudge.enviar_nudges(nudge.A4))
    assert resumo == {"candidatos": 0, "enviados": 0, "erros": 0} and "enviados" not in estado


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
