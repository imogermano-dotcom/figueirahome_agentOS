import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_sync_access
from app.integrations.imoveis_sync import sync_egorealestate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.post("/imoveis/sync/egorealestate", dependencies=[Depends(require_sync_access)])
async def sync_egorealestate_endpoint():
    try:
        return await sync_egorealestate()
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        logger.exception("Falha no sync eGO Real Estate")
        raise HTTPException(status_code=502, detail="Falha ao sincronizar com eGO Real Estate.")
