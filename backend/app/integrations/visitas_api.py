"""Visitas das oportunidades pela API do eGO (P2 de `docs/fases/api-a-substituir-scraper-acelerado-plano.md`).

`ListRealestateVisitFile` com `leadIds` e `applicationId` no corpo (sem o `applicationId` dá 401): 200 leads por pedido, ~0,5 s.
Por agora só leitura: quem compara com a tabela `visitas` é `scripts/comparar_visitas_api_relatorio.py`.
"""

import httpx

from app.config import settings
from app.integrations import ego_api


def da_api(lead_ids: list[int], lote: int = 200) -> list[dict]:
    """Todas as visitas das oportunidades `lead_ids` (ids da API), em lotes de `lote`."""
    saida: list[dict] = []
    with httpx.Client(timeout=120, headers={"User-Agent": ego_api._UA}) as c:
        s = ego_api._sessao_valida(c)
        for i in range(0, len(lead_ids), lote):
            r = c.post(f"{settings.egoapi_base_url}/realestate/Realestate/ListRealestateVisitFile", params={"applicationId": s["application_id"]},
                       json={"leadIds": lead_ids[i:i + lote], "applicationId": s["application_id"]},
                       headers={"Authorization": f"Bearer {s['token']}"})
            r.raise_for_status()
            d = r.json()
            saida += d if isinstance(d, list) else next((v for v in d.values() if isinstance(v, list)), [])
    return saida
