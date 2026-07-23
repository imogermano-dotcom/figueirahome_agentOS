import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_auth, require_sync_access
from app.db.supabase_client import get_supabase
from app.integrations.imoveis_sync import sync_egorealestate_api, sync_egorealestate_crm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.post("/imoveis/sync/egorealestate/api", dependencies=[Depends(require_sync_access)])
async def sync_egorealestate_api_endpoint():
    try:
        return await sync_egorealestate_api()
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        logger.exception("Falha no sync eGO Real Estate (API)")
        raise HTTPException(status_code=502, detail="Falha ao sincronizar com a Web API do eGO Real Estate.")


@router.post("/imoveis/sync/egorealestate/crm", dependencies=[Depends(require_sync_access)])
async def sync_egorealestate_crm_endpoint():
    try:
        return await sync_egorealestate_crm()
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        logger.exception("Falha no sync eGO Real Estate (CRM)")
        raise HTTPException(status_code=502, detail="Falha ao validar disponibilidade no CRM eGO Real Estate.")


@router.get("/imoveis/sync/log", dependencies=[Depends(require_auth)])
async def sync_log_endpoint(limit: int = 20):
    def _fetch():
        return (
            get_supabase()
            .table("agente_sync_log")
            .select("*")
            .order("executado_em", desc=True)
            .limit(limit)
            .execute()
        )

    resp = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    return resp.data


@router.delete("/imoveis/sync/log", status_code=204, dependencies=[Depends(require_auth)])
async def apagar_log_sync():
    def _delete():
        return get_supabase().table("agente_sync_log").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()

    await asyncio.get_event_loop().run_in_executor(None, _delete)
