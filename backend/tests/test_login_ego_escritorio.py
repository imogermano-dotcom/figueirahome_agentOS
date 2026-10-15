"""Login do eGO com conta de mais de um cliente (15/10).

Desde 14/10 o utilizador do scraper tem dois escritórios e o POST de login passou a devolver a página
"Log on the client" (um <select name="ApplicationID">) em vez do dashboard: o login "falhava" e os syncs
de oportunidades e de tarefas pararam em silêncio. O 2.º passo escolhe o escritório pelo nome.
"""

import asyncio
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scraper"))

import config as scraper_config  # noqa: E402
import ego_auth  # noqa: E402
import app.integrations.egorealestate_crm as crm  # noqa: E402

DASHBOARD = "<html><title>FIGUEIRAHOME</title>dashboard</html>"
ESCOLHA = (
    '<html><title>eGO Real Estate: Log on the client</title>'
    '<select name="ApplicationID"><option value="6429">FIGUEIRAHOME</option>'
    '<option value="8484">Outro Escritorio</option></select></html>'
)
SO_UM_CLIENTE = "<html><title>login</title><input name=\"username\"></html>"


def _cliente(pedidos, *, escolha=True, escritorio_ok=True):
    """Servidor falso: 1.º POST -> página de escolha; POST com ApplicationID -> dashboard."""

    def handler(req: httpx.Request) -> httpx.Response:
        corpo = req.content.decode()
        pedidos.append(corpo)
        if "ApplicationID" in corpo:
            return httpx.Response(302, headers={"location": "/egocore/dashboard"}) if escritorio_ok \
                else httpx.Response(200, text=SO_UM_CLIENTE)
        if escolha is None:
            return httpx.Response(302, headers={"location": "/egocore/dashboard"})
        return httpx.Response(200, text=ESCOLHA if escolha else SO_UM_CLIENTE)

    def dashboard(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=DASHBOARD) if req.url.path == "/egocore/dashboard" else handler(req)

    return httpx.AsyncClient(
        base_url="https://ego.exemplo", follow_redirects=True, transport=httpx.MockTransport(dashboard),
    )


@pytest.fixture(autouse=True)
def _config(monkeypatch):
    for mod, nome in ((crm.settings, "egorealestate_crm_"), (scraper_config, "egorealestate_crm_")):
        monkeypatch.setattr(mod, nome + "username", "u@exemplo.pt", raising=False)
        monkeypatch.setattr(mod, nome + "password", "segredo-de-teste", raising=False)
        monkeypatch.setattr(mod, nome + "office", "FIGUEIRAHOME", raising=False)


LOGINS = [
    pytest.param(crm._login, id="backend"),
    pytest.param(ego_auth.login, id="scraper"),
]


@pytest.mark.parametrize("login", LOGINS)
def test_conta_de_varios_clientes_escolhe_o_escritorio_pelo_nome(login):
    pedidos: list[str] = []
    asyncio.run(login(_cliente(pedidos)))
    assert len(pedidos) == 2
    assert "ApplicationID=6429" in pedidos[1]  # FIGUEIRAHOME, não o outro


@pytest.mark.parametrize("login", LOGINS)
def test_conta_de_um_so_cliente_continua_a_funcionar_sem_2o_passo(login):
    pedidos: list[str] = []
    asyncio.run(login(_cliente(pedidos, escolha=None)))
    assert len(pedidos) == 1 and "ApplicationID" not in pedidos[0]


@pytest.mark.parametrize("login", LOGINS)
def test_escritorio_inexistente_diz_quais_ha(login, monkeypatch):
    monkeypatch.setattr(crm.settings, "egorealestate_crm_office", "NAO EXISTE", raising=False)
    monkeypatch.setattr(scraper_config, "egorealestate_crm_office", "NAO EXISTE", raising=False)
    with pytest.raises(RuntimeError, match="não está entre"):
        asyncio.run(login(_cliente([])))


@pytest.mark.parametrize("login", LOGINS)
def test_login_que_continua_na_pagina_de_login_falha_como_antes(login):
    with pytest.raises(RuntimeError, match="Login no CRM eGO falhou"):
        asyncio.run(login(_cliente([], escolha=False)))


@pytest.mark.parametrize("login", LOGINS)
def test_nome_do_escritorio_ignora_maiusculas(login, monkeypatch):
    monkeypatch.setattr(crm.settings, "egorealestate_crm_office", "figueirahome", raising=False)
    monkeypatch.setattr(scraper_config, "egorealestate_crm_office", "figueirahome", raising=False)
    pedidos: list[str] = []
    asyncio.run(login(_cliente(pedidos)))
    assert "ApplicationID=6429" in pedidos[1]
