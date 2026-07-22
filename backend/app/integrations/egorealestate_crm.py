"""Cliente para o backoffice autenticado do eGO Real Estate (não a Web API
pública). Necessário porque a Web API só devolve imóveis publicados — o
backoffice tem visibilidade total (incl. "Por validar", rascunhos, etc).

Login é um POST de formulário clássico (sem token CSRF), confirmado via
leitura do `Authentication.min.js` do próprio backoffice:
`Authentication.login` faz `window.post(window.location, $("#loginForm").serializeAll(":input"))`.
"""

import logging

import httpx
from bs4 import BeautifulSoup

from app.config import settings

logger = logging.getLogger(__name__)

_LOGIN_PATH = "/egocore?ReturnURL=%2fegocore%2fdashboard"
_SEARCH_PATH = "/egocore/search/realestatesearch"

# Códigos de "status" do filtro da listagem do backoffice (confirmados ao vivo,
# sessão 2026-07-21, sondando 0-14). O portefólio tem ~5082 imóveis no total,
# mas a esmagadora maioria está em "Em Prospecção" (status=7) — fase de
# angariação que nunca chegou a virar imóvel com referência formal (0 resultados
# com Reference nesse status). Vendido (3) e Retirado (8) também ficaram de fora:
# testados ao vivo, têm ~1900 itens combinados (histórico acumulado de anos,
# quase certo sem correspondência na nossa tabela `imoveis` de ~180 linhas) —
# só valem a pena se um dia detectarmos essa deriva especificamente (imóvel
# nosso "Disponível" que na realidade já foi vendido/retirado no CRM).
_STATUS_CODES = {
    2: "Disponível",
    4: "Reservado",
    5: "Arrendado",
    9: "Por validar",
}


async def _login(client: httpx.AsyncClient) -> None:
    if not settings.egorealestate_crm_username or not settings.egorealestate_crm_password:
        raise RuntimeError("EGOREALESTATE_CRM_USERNAME/PASSWORD não configuradas.")

    resp = await client.post(
        _LOGIN_PATH,
        data={
            "username": settings.egorealestate_crm_username,
            "password": settings.egorealestate_crm_password,
        },
    )
    resp.raise_for_status()
    if "/egocore/dashboard" not in str(resp.url) and "/egocore/realestates" not in str(resp.url):
        raise RuntimeError("Login no CRM eGO falhou — credenciais inválidas ou fluxo de login mudou.")


def _parse_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for item in soup.select(".listItem.propertyItem"):
        # imóveis que são fracções de um empreendimento têm um span extra
        # ("Fração"/"Empreendimento") antes do span com a referência real —
        # excluir explicitamente em vez de confiar em ser o primeiro/último.
        ref_span = item.select_one(".ListItemTitle a span:not(.developmentTitle)")
        status_div = item.select_one(".listItemStatus")
        checkbox = item.select_one(".ObjectChecker")
        if not ref_span or not status_div or not checkbox:
            continue
        ego_id = checkbox.get("data-object-id")
        items.append({
            "imovel_ref": ref_span.get_text(strip=True),
            "crm_disponibilidade": status_div.get_text(strip=True),
            "ego_id": int(ego_id) if ego_id else None,
        })
    return items


async def _fetch_status(client: httpx.AsyncClient, status: int) -> list[dict]:
    results: list[dict] = []
    page = 1
    while True:
        resp = await client.post(_SEARCH_PATH, data={
            "status": status, "Page": page, "listSortDirection": 0, "viewType": 0, "ParentID": 0,
        })
        resp.raise_for_status()
        body = resp.json()
        html = (body.get("replaces") or {}).get("#RealestateListResults", "")
        batch = _parse_page(html)
        if not batch:
            break
        results.extend(batch)
        page += 1
    return results


async def fetch_all() -> list[dict]:
    """Percorre a listagem do backoffice filtrada pelos estados com referência
    real (ver `_STATUS_CODES`), devolve [{imovel_ref, crm_disponibilidade, ego_id}, ...]."""
    results: list[dict] = []
    async with httpx.AsyncClient(base_url=settings.egorealestate_crm_base_url, timeout=30, follow_redirects=True) as client:
        await _login(client)
        for status in _STATUS_CODES:
            results.extend(await _fetch_status(client, status))
    return results
