"""Nenhum teste pode disparar tráfego real para serviços externos.

Achado a 2026-08-31: `test_promocao_nao_repete` chama `guards.promover_se_qualificada`
sem mockar `notificar` nem as settings -- inofensivo enquanto o `.env` não tinha
credenciais do Resend, mas assim que ficaram preenchidas (troca de Microsoft
Graph por Resend, mesma sessão) a suite passou a mandar um email real, de
verdade, para o director, com os dados fictícios do teste ("Isabel Braga").

Zera as credenciais de notificação antes de cada teste; quem precisar de as
testar a sério preenche-as explicitamente dentro do próprio teste (ver
`test_notificacoes.py::_configurar`), depois deste fixture já ter corrido.
"""

import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def _sem_credenciais_reais_de_notificacao(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "")
    monkeypatch.setattr(settings, "resend_remetente", "")
    monkeypatch.setattr(settings, "notificacoes_para", "")


@pytest.fixture(autouse=True)
def _sem_consulta_real_das_oportunidades(monkeypatch):
    """A escalada procura as oportunidades do telefone (`notificacoes.consultoras_do_telefone`): nunca na base real nos testes.
    Quem a testa a sério repõe a função dentro do próprio teste."""
    import app.agents.broker.tools as tools

    monkeypatch.setattr(tools, "consultoras_do_telefone", lambda telefone: {"ops": [], "nomes": [], "emails": []})


@pytest.fixture(autouse=True)
def _sem_extrator_mql_real(monkeypatch):
    """`_extrair_mql_do_resumo` é uma chamada ao modelo: nunca a sério nos testes (resposta sem tool = `{}`).
    Quem a testa substitui `messages.create` ou a própria função dentro do teste."""
    import app.agents.broker.tools as tools

    async def _sem_resposta(**kwargs):
        return type("R", (), {"content": []})()

    monkeypatch.setattr(tools._anthropic.messages, "create", _sem_resposta)


WIDGET_CHAT_SECRET_DE_TESTE ="segredo-de-teste"


@pytest.fixture(autouse=True)
def _widget_chat_secret_de_teste(monkeypatch):
    """Chave fixa e conhecida, nunca a real do Fly -- `test_site_chat.py` usa
    esta constante para montar o header `X-Widget-Key` esperado."""
    monkeypatch.setattr(settings, "widget_chat_secret", WIDGET_CHAT_SECRET_DE_TESTE)
