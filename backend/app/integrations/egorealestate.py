"""Cliente fino para a Web API do eGO Real Estate (CRM da agência).

Base http://websiteapi.egorealestate.com, auth via header `AuthorizationToken`
— chave da **agência**, não de utilizador. É por isso que a Web API devolve
imóveis que o backoffice recusa mostrar à conta do backend (ver
`egorealestate_crm.py`): duas portas, credenciais de âmbitos diferentes.

**Dois endpoints de leitura, e o de listagem não é o completo** (medido
2026-08-18 no FH2572):

* `GET /v1/Properties` — paginado, **82 campos**. Alimenta a grelha de
  resultados de um site: miniatura, preço, tipologia, localização.
* `GET /v1/Properties/{ID}` — **104 campos**, superset (zero campos exclusivos
  da listagem). Alimenta a página do imóvel.

Os 22 campos extra são os que só uma página de detalhe usa, e há coisas reais
lá dentro: `ExternalVirtualTours` (as "Visitas virtuais externas" do backoffice
— Matterport), `ExtraLinks` (espelho do anterior), `Brochures`, `PDF`,
`Panoramic`, `PropertyDevelopment`, `SEODescription`/`SEOKeywords`,
`FinancingConditions`, `Co2Efficiency`, `ThermalInsulationEfficiency`.

⚠️ Não assumir que a listagem tem tudo — foi o erro que fez concluir que o eGO
não expunha visitas virtuais e que só o backoffice as teria. `get_properties_page`
usa a listagem porque o sync só precisa desses campos; **capturar os restantes
custa uma chamada por imóvel** (~56 por sync), e a app principal já morreu por
OOM com menos do que isso — ver a decisão dos 512mb em `docs/decisoes.md`.

`/v1/Properties/Latest` (sync incremental por Since) foi testado ao vivo e
confirmado avariado do lado do eGO — ignora Since (devolve sempre só o
imóvel mais recentemente alterado, independentemente do valor enviado,
incl. datas no futuro). Por isso sync_egorealestate_api() faz sempre full-sync
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
