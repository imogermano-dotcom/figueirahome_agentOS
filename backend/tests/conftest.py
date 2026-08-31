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
