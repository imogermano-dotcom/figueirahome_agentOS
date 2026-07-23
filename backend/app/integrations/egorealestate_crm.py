"""Cliente para o backoffice autenticado do eGO Real Estate (não a Web API
pública). Necessário porque a Web API só devolve imóveis publicados — o
backoffice tem visibilidade total (incl. "Por validar", rascunhos, etc).

Login é um POST de formulário clássico (sem token CSRF), confirmado via
leitura do `Authentication.min.js` do próprio backoffice:
`Authentication.login` faz `window.post(window.location, $("#loginForm").serializeAll(":input"))`.
"""

import logging
import re

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


async def fetch_all(client: httpx.AsyncClient) -> list[dict]:
    """Percorre a listagem do backoffice filtrada pelos estados com referência
    real (ver `_STATUS_CODES`), devolve [{imovel_ref, crm_disponibilidade, ego_id}, ...].
    `client` já deve estar autenticado (ver `_login`)."""
    results: list[dict] = []
    for status in _STATUS_CODES:
        results.extend(await _fetch_status(client, status))
    return results


async def find_by_ref(client: httpx.AsyncClient, ref: str) -> dict | None:
    """Pesquisa livre no backoffice por referência (campo `FreeText` — o único
    nome de parâmetro aceite pelo endpoint; confirmado lendo `Search.inputKeyUp`
    em Startup.min.js, `searchText` é ignorado silenciosamente). Ao contrário de
    `fetch_all`, não filtra por status — cobre também "Retirado"/"Vendido"/
    "Em Prospecção", útil para reencontrar o `ego_id` novo de um imóvel
    recriado no eGO. `client` já deve estar autenticado (ver `_login`)."""
    resp = await client.post(_SEARCH_PATH, data={
        "FreeText": ref, "Page": 1, "listSortDirection": 0, "viewType": 0, "ParentID": 0,
    })
    resp.raise_for_status()
    body = resp.json()
    html = (body.get("replaces") or {}).get("#RealestateListResults", "")
    for item in _parse_page(html):
        if item["imovel_ref"] == ref:
            return item
    return None


def authenticated_client() -> httpx.AsyncClient:
    """Sessão httpx com a base_url do backoffice — chamar `await _login(client)`
    antes de usar. Devolvida sem login para o caller poder reutilizar a mesma
    sessão em várias chamadas (`fetch_all` + `fetch_detail`) com 1 só login."""
    return httpx.AsyncClient(base_url=settings.egorealestate_crm_base_url, timeout=30, follow_redirects=True)


def _clean(s: str | None) -> str | None:
    return s.replace("\xa0", " ").strip() if s else s


def _parse_preco(s: str | None) -> float | None:
    s = _clean(s)
    digits = re.sub(r"[^\d]", "", s) if s else ""
    return float(digits) if digits else None


def _parse_int(s: str | None) -> int | None:
    s = _clean(s)
    digits = re.sub(r"[^\d]", "", s) if s else ""
    return int(digits) if digits else None


def _parse_area(s: str | None) -> float | None:
    s = _clean(s)
    m = re.search(r"[\d.,]+", s) if s else None
    return float(m.group(0).replace(",", ".")) if m else None


def _parse_detail(html: str, ego_id: int) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")

    title_p = soup.select_one("p.listHeaderTitle")
    ref_span = title_p.select_one("span") if title_p else None
    if not title_p or not ref_span:
        return None
    imovel_ref = ref_span.get_text(strip=True)
    titulo = title_p.get_text(strip=True).replace(imovel_ref, "").strip() or None

    freguesia = concelho = None
    subtitle = soup.select_one("p.listHeaderSubTitle")
    if subtitle:
        parts = [p.strip() for p in subtitle.get_text(strip=True).split(",")]
        if len(parts) == 2:
            freguesia, concelho = parts

    venda_preco = arrendamento_preco = None
    for section in soup.select(".listItemPricingSection"):
        strong = section.select_one("strong")
        if not strong:
            continue
        texto = section.get_text(strip=True)
        valor = _parse_preco(strong.get_text(strip=True))
        if texto.startswith("Venda"):
            venda_preco = valor
        elif texto.startswith("Arrendamento"):
            arrendamento_preco = valor

    campos: dict[str, str] = {}
    for span in soup.select(".listItemData .listItemDataSection"):
        strong = span.select_one("strong")
        if not strong:
            continue
        valor = strong.get_text(strip=True)
        label = span.get_text(strip=True).replace(valor, "").strip()
        campos[label] = valor

    # A descrição real e o bloco de "Características" (infraestruturas) usam
    # ambos a classe .listItemDescription — identificar pelo título da secção
    # anterior em vez de assumir que a descrição é sempre a primeira ocorrência.
    descricao = None
    for title_div in soup.select(".detailPropertyContentTitle"):
        if "Descri" in title_div.get_text(strip=True):
            content = title_div.find_next_sibling("div", class_="listItemDescription")
            if content:
                descricao = content.get_text("\n", strip=True)
            break

    fotos: list[str] = []
    for img in soup.select("img[src*='Tphoto']"):
        src = img.get("src")
        if src and src not in fotos:
            fotos.append(src)

    return {
        "imovel_ref": imovel_ref,
        "titulo": titulo,
        "freguesia": freguesia,
        "concelho": concelho,
        "venda_preco": venda_preco,
        "arrendamento_preco": arrendamento_preco,
        "estado": campos.get("Estado"),
        "disponibilidade": campos.get("Disponibilidade"),
        "quartos": _parse_int(campos.get("Quartos")),
        "casas_banho": _parse_int(campos.get("Casas de banho")),
        "area_util": _parse_area(campos.get("Área útil")),
        "area_bruta": _parse_area(campos.get("Área bruta")),
        "certificacao_energetica": campos.get("Certificação Energética"),
        "descricao": descricao,
        "fotos": fotos,
        "foto_principal": fotos[0] if fotos else None,
        "ego_id": ego_id,
        "fonte": "egorealestate",
    }


async def fetch_detail(client: httpx.AsyncClient, ego_id: int) -> dict | None:
    """Página de detalhe do backoffice (visibilidade total, qualquer estado)
    — usada para criar linhas novas e para reler o estado real de uma linha
    específica. `client` já deve estar autenticado (ver `_login`)."""
    resp = await client.get(f"/egocore/realestate/{ego_id}")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return _parse_detail(resp.text, ego_id)
