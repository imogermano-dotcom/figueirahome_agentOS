"""Login no backoffice do eGO Real Estate — cópia mínima de
`backend/app/integrations/egorealestate_crm.py::_login`/`authenticated_client`
(POST de formulário, sem CSRF). Duplicado em vez de importado para o serviço
`scraper/` não arrastar as dependências do backend principal (bs4, parsing de
detalhe de imóvel) que aqui não são precisas.
"""
import httpx

import config

_LOGIN_PATH = "/egocore?ReturnURL=%2fegocore%2fdashboard"


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
