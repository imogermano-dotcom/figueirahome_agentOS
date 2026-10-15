"""Login no backoffice do eGO Real Estate — cópia mínima de
`backend/app/integrations/egorealestate_crm.py::_login`/`authenticated_client`
(POST de formulário, sem CSRF). Duplicado em vez de importado para o serviço
`scraper/` não arrastar as dependências do backend principal (bs4, parsing de
detalhe de imóvel) que aqui não são precisas.
"""
import re

import httpx

import config

_LOGIN_PATH = "/egocore?ReturnURL=%2fegocore%2fdashboard"


# Conta com mais de um cliente (15/10: o utilizador ganhou um 2.º escritório): o login passa a ter um
# 2.º passo, "Log on the client", com um <select name="ApplicationID">. Sem escolher o escritório o
# POST devolve essa página e o login "falhava" (14/10: sync de oportunidades e de tarefas parados).
_SELECT_ESCRITORIO = re.compile(r'<select[^>]*name="ApplicationID"[^>]*>(.*?)</select>', re.S | re.I)
_OPCAO = re.compile(r'<option[^>]*value="(\d+)"[^>]*>([^<]*)</option>', re.I)


def _id_do_escritorio(html: str, nome: str) -> str | None:
    """ID do escritório `nome` no passo "Log on the client", ou None se a página não tem seletor
    (conta com um só cliente). Levanta se o seletor existe mas o escritório não está lá."""
    m = _SELECT_ESCRITORIO.search(html)
    if not m:
        return None
    opcoes = _OPCAO.findall(m.group(1))
    for id_, rotulo in opcoes:
        if rotulo.strip().lower() == nome.strip().lower():
            return id_
    raise RuntimeError(
        f"Login no CRM eGO: o escritório '{nome}' não está entre {[r.strip() for _, r in opcoes]}."
    )


async def login(client: httpx.AsyncClient) -> None:
    if not config.egorealestate_crm_username or not config.egorealestate_crm_password:
        raise RuntimeError("EGOREALESTATE_CRM_USERNAME/PASSWORD não configuradas.")

    resp = await client.post(
        _LOGIN_PATH,
        data={
            "username": config.egorealestate_crm_username,
            "password": config.egorealestate_crm_password,
        },
    )
    resp.raise_for_status()
    if "/egocore/dashboard" not in str(resp.url) and "/egocore/realestates" not in str(resp.url):
        escritorio = _id_do_escritorio(resp.text, config.egorealestate_crm_office)
        if escritorio:
            resp = await client.post(
                _LOGIN_PATH,
                data={
                    "username": config.egorealestate_crm_username,
                    "password": config.egorealestate_crm_password,
                    "ApplicationID": escritorio,
                },
            )
            resp.raise_for_status()
    if "/egocore/dashboard" not in str(resp.url) and "/egocore/realestates" not in str(resp.url):
        raise RuntimeError("Login no CRM eGO falhou — credenciais inválidas ou fluxo de login mudou.")


def authenticated_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=config.egorealestate_crm_base_url, timeout=30, follow_redirects=True)


async def session_cookies() -> list[dict]:
    async with authenticated_client() as client:
        await login(client)
        return [
            {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path or "/"}
            for c in client.cookies.jar
        ]
