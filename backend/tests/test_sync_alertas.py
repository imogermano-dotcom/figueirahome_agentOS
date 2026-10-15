"""Aviso de falha dos syncs do eGO (15/10).

O login do CRM falhou a 14/10 e os syncs de oportunidades e de tarefas ficaram parados dois dias sem
ninguém saber (só os sucessos iam para `agente_sync_log`). Agora uma falha do cron fica registada e
avisa o director e os `alertas_para`; uma falha manual só fica registada (quem carregou no botão vê o erro).
"""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from app import notificacoes
from app.api import oportunidades_sync
from app.config import settings


@pytest.fixture
def mundo(monkeypatch):
    registo = {"logs": [], "avisos": []}

    class _Q:
        def insert(self, dados):
            registo["logs"].append(dados)
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    monkeypatch.setattr("app.db.supabase_client.get_supabase", lambda: SimpleNamespace(table=lambda n: _Q()))
    monkeypatch.setattr(
        notificacoes, "notificar",
        lambda assunto, corpo, imovel_ref=None, para_extra=None: registo["avisos"].append((assunto, corpo, para_extra)),
    )
    monkeypatch.setattr(settings, "alertas_para", "eu@exemplo.pt, outro@exemplo.pt")
    return registo


def test_falha_do_cron_regista_e_avisa(mundo):
    asyncio.run(notificacoes.falha_de_sync("egorealestate_tarefas", "tarefas", "cron", "Login no CRM eGO falhou"))

    assert mundo["logs"] == [{"tipo": "egorealestate_tarefas_erro", "resumo": {"erro": "Login no CRM eGO falhou"}, "origem": "cron"}]
    (assunto, corpo, extra), = mundo["avisos"]
    assert assunto == "Sync falhou — tarefas" and "Login no CRM eGO falhou" in corpo
    assert extra == ["eu@exemplo.pt", "outro@exemplo.pt"]


def test_falha_manual_so_regista(mundo):
    asyncio.run(notificacoes.falha_de_sync("egorealestate_tarefas", "tarefas", "manual", "erro"))
    assert len(mundo["logs"]) == 1 and mundo["avisos"] == []


def test_o_aviso_nunca_levanta(mundo, monkeypatch):
    def _rebenta(*a, **k):
        raise RuntimeError("Resend em baixo")

    monkeypatch.setattr(notificacoes, "notificar", _rebenta)
    asyncio.run(notificacoes.falha_de_sync("egorealestate_tarefas", "tarefas", "cron", "erro"))  # não levanta


def test_o_registo_a_falhar_nao_impede_o_aviso(mundo, monkeypatch):
    def _rebenta():
        raise RuntimeError("base em baixo")

    monkeypatch.setattr("app.db.supabase_client.get_supabase", _rebenta)
    asyncio.run(notificacoes.falha_de_sync("egorealestate_tarefas", "tarefas", "cron", "erro"))
    assert len(mundo["avisos"]) == 1


def test_detalhe_enorme_e_cortado(mundo):
    asyncio.run(notificacoes.falha_de_sync("egorealestate_tarefas", "tarefas", "cron", "x" * 5000))
    assert len(mundo["logs"][0]["resumo"]["erro"]) == 500


def test_notificar_junta_os_extras_sem_duplicar(monkeypatch):
    enviados = {}
    monkeypatch.setattr(settings, "resend_api_key", "k")
    monkeypatch.setattr(settings, "resend_remetente", "avisos@exemplo.pt")
    monkeypatch.setattr(settings, "notificacoes_para", "diretor@exemplo.pt")

    def _post(url, headers=None, json=None, timeout=None):
        enviados.update(json)
        return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr(notificacoes.httpx, "post", _post)
    notificacoes.notificar("a", "b", para_extra=["eu@exemplo.pt", "diretor@exemplo.pt"])
    assert enviados["to"] == ["diretor@exemplo.pt", "eu@exemplo.pt"]


def test_endpoint_de_tarefas_avisa_quando_o_scraper_falha(monkeypatch):
    chamadas = []

    async def _falha(tipo, nome, origem, detalhe):
        chamadas.append((tipo, nome, origem))

    class _Cliente:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): raise httpx.ConnectError("sem rede")

    monkeypatch.setattr(oportunidades_sync, "falha_de_sync", _falha)
    monkeypatch.setattr(oportunidades_sync.httpx, "AsyncClient", _Cliente)
    monkeypatch.setattr(settings, "scraper_service_url", "https://scraper.exemplo")
    monkeypatch.setattr(settings, "scraper_service_secret", "s")

    with pytest.raises(HTTPException) as e:
        asyncio.run(oportunidades_sync.sync_tarefas_endpoint(acesso="sync-secret"))
    assert e.value.status_code == 502
    assert chamadas == [("egorealestate_tarefas", "tarefas", "cron")]
