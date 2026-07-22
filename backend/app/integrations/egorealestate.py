"""Cliente fino para a Web API do eGO Real Estate (CRM da agência).

Doc oficial: base http://websiteapi.egorealestate.com, auth via header
AuthorizationToken. Ver GET /v1/Properties.

`/v1/Properties/Latest` (sync incremental por Since) foi testado ao vivo e
confirmado avariado do lado do eGO — ignora Since (devolve sempre só o
imóvel mais recentemente alterado, independentemente do valor enviado,
incl. datas no futuro). Por isso sync_egorealestate() faz sempre full-sync
paginado via get_properties_page, sem depender de Latest.
"""

import httpx

from app.config import settings


def _headers() -> dict:
    return {
        "AuthorizationToken": settings.egorealestate_api_key,
        "Language": settings.egorealestate_language,
    }


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
