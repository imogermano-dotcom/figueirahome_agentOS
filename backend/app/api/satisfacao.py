import logging

from fastapi import APIRouter, Depends, HTTPException

from app.agents.broker.satisfacao import enviar_inqueritos
from app.api.deps import require_automacao_access

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# Cron `satisfacao-enviar` (crons/schedules.json). A janela 9h–20h e o interruptor estão no portal
# (fn_satisf_para_enviar / satisfacao_config.ligado): fora deles a fila vem vazia.
@router.post("/satisfacao/enviar")
async def enviar_satisfacao_endpoint(acesso=Depends(require_automacao_access)):
    try:
        return await enviar_inqueritos()
    except Exception:
        logger.exception("Falha a enviar os inquéritos de satisfação")
        raise HTTPException(status_code=502, detail="Falha a enviar os inquéritos de satisfação.")
