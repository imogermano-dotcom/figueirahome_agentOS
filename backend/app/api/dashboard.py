import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_auth
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])


@router.get("/dashboard")
async def dashboard():
    """Métricas do painel — uma RPC, um round-trip.

    Antes eram 5 queries em série sobre as tabelas do agente (1 a 5 linhas cada),
    deixando de fora as 25 mil oportunidades e os 4462 imóveis. A agregação vive
    agora em `dashboard_metricas()` (migration 0015): contar isto do lado do
    cliente não é opção.
    """

    def _fetch():
        return get_supabase().rpc("dashboard_metricas").execute()

    try:
        resp = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    except Exception:
        logger.exception("Erro ao obter métricas do dashboard")
        raise HTTPException(status_code=500, detail="Erro ao obter métricas.")

    return resp.data or {}
