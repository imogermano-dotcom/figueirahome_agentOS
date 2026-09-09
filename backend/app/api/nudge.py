import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_automacao_access
from app.agents.broker.nudge import enviar_nudges

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.post("/matilde/nudge")
async def enviar_nudges_endpoint(acesso=Depends(require_automacao_access)):
    try:
        return await enviar_nudges()
    except Exception:
        logger.exception("Falha a correr o nudge da Matilde")
        raise HTTPException(status_code=502, detail="Falha a correr o nudge da Matilde.")
