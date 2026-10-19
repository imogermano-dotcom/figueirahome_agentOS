"""Sync de oportunidades: «0 resultados» deixa de ser falha (`app/api/oportunidades_sync.py`).

Corre com `pytest backend/tests/` ou `python backend/tests/test_oportunidades_sync_sem_alteracoes.py`. Sem rede.
Caso real de 19/10: segunda-feira, nenhuma oportunidade editada durante o fim de semana, o filtro «Últimas 48 horas»
deu 0 resultados, o eGO não mostrou o botão Relatórios e o scraper levantou 'Link "Relatórios" não encontrado'.
O aviso de falha foi por email ao diretor sem haver falha nenhuma.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import oportunidades_sync as sync  # noqa: E402
from app.api.deps import require_sync_access  # noqa: E402
from app.config import settings  # noqa: E402
from app.integrations import ego_api  # noqa: E402

ERRO = '{"detail":"Link \\"Relatórios\\" não encontrado — selecção pode ter falhado (0 resultados?)."}'


def _ha(horas: float) -> str:
    return (datetime.now(ZoneInfo("Europe/Lisbon")).replace(tzinfo=None) - timedelta(hours=horas)).isoformat(timespec="seconds")


def test_editadas_desde_conta_so_as_da_janela(monkeypatch):
    lista = [{"alterDate": _ha(1)}, {"alterDate": _ha(47)}, {"alterDate": _ha(49)}, {"alterDate": _ha(100)}, {"alterDate": None}, {}]
    monkeypatch.setattr(ego_api, "_pedido", lambda *a, **k: {"opportunities": lista, "totalRows": 6})
    assert ego_api.oportunidades_editadas_desde(48) == 2
    assert ego_api.oportunidades_editadas_desde(24) == 1


def test_editadas_desde_sem_nenhuma(monkeypatch):
    monkeypatch.setattr(ego_api, "_pedido", lambda *a, **k: {"opportunities": [{"alterDate": _ha(72)}]})
    assert ego_api.oportunidades_editadas_desde(48) == 0


def _api(monkeypatch, editadas=None, rebenta=False):
    chamadas = []

    def _f(horas):
        chamadas.append(horas)
        if rebenta:
            raise RuntimeError("503")
        return editadas

    monkeypatch.setattr(sync.ego_api, "oportunidades_editadas_desde", _f)
    return chamadas


def test_helper_sem_resultados_e_api_a_zero_nao_e_falha(monkeypatch):
    import asyncio
    chamadas = _api(monkeypatch, editadas=0)
    assert asyncio.run(sync._sem_alteracoes(ERRO)) is True and chamadas == [48]


def test_helper_com_edicoes_na_api_continua_a_ser_falha(monkeypatch):
    import asyncio
    _api(monkeypatch, editadas=3)
    assert asyncio.run(sync._sem_alteracoes(ERRO)) is False


def test_helper_outro_erro_nem_pergunta_a_api(monkeypatch):
    import asyncio
    chamadas = _api(monkeypatch, editadas=0)
    assert asyncio.run(sync._sem_alteracoes('{"detail":"Sessão não autenticou"}')) is False and chamadas == []


def test_helper_api_em_baixo_continua_a_ser_falha(monkeypatch):
    import asyncio
    _api(monkeypatch, rebenta=True)
    assert asyncio.run(sync._sem_alteracoes(ERRO)) is False


class _ClienteQueFalha:
    """Duplo do httpx.AsyncClient: o scraper responde 500 com o erro."""

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **k):
        return httpx.Response(500, text=ERRO, request=httpx.Request("POST", url))


def _endpoint(monkeypatch):
    registos, avisos = [], []
    monkeypatch.setattr(settings, "scraper_service_url", "http://scraper.invalid")
    monkeypatch.setattr(settings, "scraper_service_secret", "x")
    monkeypatch.setattr(sync.httpx, "AsyncClient", _ClienteQueFalha)

    async def _log(resumo, origem, tipo="egorealestate_oportunidades_completo"):
        registos.append((resumo, origem))

    async def _aviso(*a, **k):
        avisos.append(a)

    monkeypatch.setattr(sync, "_log_execucao", _log)
    monkeypatch.setattr(sync, "falha_de_sync", _aviso)
    app = FastAPI()
    app.include_router(sync.router)
    app.dependency_overrides[require_sync_access] = lambda: "sync-secret"
    return TestClient(app), registos, avisos


def test_endpoint_sem_edicoes_regista_normal_e_nao_avisa(monkeypatch):
    _api(monkeypatch, editadas=0)
    cliente, registos, avisos = _endpoint(monkeypatch)
    r = cliente.post("/api/oportunidades/sync/completo")
    assert r.status_code == 200 and r.json()["sem_alteracoes"] is True
    assert avisos == [], "sem email ao diretor"
    assert registos and registos[0][0]["sem_alteracoes"] is True and registos[0][1] == "cron"


def test_endpoint_com_edicoes_continua_a_falhar_e_a_avisar(monkeypatch):
    _api(monkeypatch, editadas=5)
    cliente, registos, avisos = _endpoint(monkeypatch)
    r = cliente.post("/api/oportunidades/sync/completo")
    assert r.status_code == 502 and registos == [] and len(avisos) == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
