import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_automacao_access
from app.agents.broker.nudge import enviar_todos_nudges

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# Caminho e nome ficaram "matilde" por compatibilidade com o cron já
# registado (`crons/schedules.json`, nudge-matilde) — mudar o nome apaga o
# histórico de execuções. Cobre A1/A3/A4 desde 25/09.
@router.post("/matilde/nudge")
async def enviar_nudges_endpoint(acesso=Depends(require_automacao_access)):
    try:
        return await enviar_todos_nudges()
    except Exception:
        logger.exception("Falha a correr o nudge dos assistentes")
        raise HTTPException(status_code=502, detail="Falha a correr o nudge dos assistentes.")
