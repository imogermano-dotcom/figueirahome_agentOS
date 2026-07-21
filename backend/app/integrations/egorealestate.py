"""Cliente fino para a Web API do eGO Real Estate (CRM da agência).

Doc oficial: base http://websiteapi.egorealestate.com, auth via header
AuthorizationToken. Ver GET /v1/Properties, /v1/Properties/Latest.
"""

from datetime import datetime

import httpx

from app.config import settings


def _headers() -> dict:
    return {
        "AuthorizationToken": settings.egorealestate_api_key,
        "Language": settings.egorealestate_language,
    }


async def get_latest(since: datetime) -> list[dict]:
    """IDs + DateAltered de propriedades alteradas desde `since` (UTC)."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{settings.egorealestate_base_url}/v1/Properties/Latest",
            headers=_headers(),
            params={"Since": since.strftime("%Y-%m-%dT%H:%M:%SZ")},
        )
        resp.raise_for_status()
        return resp.json().get("Properties", [])


async def get_properties_by_ids(ids: list[int]) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{settings.egorealestate_base_url}/v1/Properties",
            headers=_headers(),
            params={"IDS": ",".join(str(i) for i in ids)},
        )
        resp.raise_for_status()
        return resp.json().get("Properties", [])


async def get_properties_page(page: int, per_page: int = 100) -> tuple[list[dict], int]:
    """Uma página da listagem completa (sem filtros) — usada no full sync inicial."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{settings.egorealestate_base_url}/v1/Properties",
            headers=_headers(),
            params={"PAG": page, "NRE": per_page},
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("Properties", []), data.get("TotalRecords", 0)
