import asyncio
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_auth, require_sync_access
from app.config import settings
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


async def _log_execucao(resumo: dict, origem: str, tipo: str = "egorealestate_oportunidades_completo") -> None:
    def _insert():
        return get_supabase().table("agente_sync_log").insert({
            "tipo": tipo, "resumo": resumo, "origem": origem,
        }).execute()

    await asyncio.get_event_loop().run_in_executor(None, _insert)


@router.post("/oportunidades/sync/completo")
async def sync_oportunidades_completo_endpoint(acesso=Depends(require_sync_access)):
    origem = "cron" if acesso == "sync-secret" else "manual"
    if not settings.scraper_service_url or not settings.scraper_service_secret:
        raise HTTPException(status_code=502, detail="SCRAPER_SERVICE_URL/SECRET não configurados.")

    try:
        async with httpx.AsyncClient(timeout=240) as client:
            resp = await client.post(
                f"{settings.scraper_service_url}/run/oportunidades-completo",
                headers={"X-Scraper-Secret": settings.scraper_service_secret},
            )
            resp.raise_for_status()
            resumo = resp.json()
    except httpx.HTTPStatusError as e:
        logger.exception("Scraper devolveu erro no sync de oportunidades (relatório completo)")
        raise HTTPException(status_code=502, detail=e.response.text)
    except Exception:
        logger.exception("Falha ao contactar o serviço de scraping de oportunidades")
        raise HTTPException(status_code=502, detail="Falha ao contactar o serviço de scraping.")

    await _log_execucao(resumo, origem)
    return resumo


@router.post("/oportunidades/sync/tarefas")
async def sync_tarefas_endpoint(acesso=Depends(require_sync_access)):
    """Snapshot das tarefas activas do eGO (4 relatórios em fatias, ~150 s no PC;
    tecto de 600 s para o Fly). Mesmo desenho do `completo`: o backend guarda o
    segredo do scraper e grava o resumo em `agente_sync_log`."""
    origem = "cron" if acesso == "sync-secret" else "manual"
    if not settings.scraper_service_url or not settings.scraper_service_secret:
        raise HTTPException(status_code=502, detail="SCRAPER_SERVICE_URL/SECRET não configurados.")

    try:
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.post(
                f"{settings.scraper_service_url}/run/tarefas",
                headers={"X-Scraper-Secret": settings.scraper_service_secret},
            )
            resp.raise_for_status()
            resumo = resp.json()
    except httpx.HTTPStatusError as e:
        logger.exception("Scraper devolveu erro no sync de tarefas")
        raise HTTPException(status_code=502, detail=e.response.text)
    except Exception:
        logger.exception("Falha ao contactar o serviço de scraping de tarefas")
        raise HTTPException(status_code=502, detail="Falha ao contactar o serviço de scraping.")

    await _log_execucao(resumo, origem, tipo="egorealestate_tarefas")
    return resumo


@router.get("/oportunidades/sync/log", dependencies=[Depends(require_auth)])
async def oportunidades_sync_log_endpoint(limit: int = 20):
    def _fetch():
        return (
            get_supabase()
            .table("agente_sync_log")
            .select("*")
            .eq("tipo", "egorealestate_oportunidades_completo")
            .order("executado_em", desc=True)
            .limit(limit)
            .execute()
        )

    resp = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    return resp.data
