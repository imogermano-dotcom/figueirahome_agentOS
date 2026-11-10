import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import notificacoes
from app.api.deps import require_n8n_access

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class FalhaDeFluxo(BaseModel):
    workflow: str = ""
    no: str = ""
    erro: str = ""
    execucao: str = ""


# n8n, workflow «Alerta de falhas» (Error Workflow dos fluxos críticos). `?dry=1` não envia nem regista.
@router.post("/n8n/falhou")
async def n8n_falhou(corpo: FalhaDeFluxo, dry: int = 0, acesso=Depends(require_n8n_access)):
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, notificacoes.falha_de_workflow, corpo.workflow, corpo.no, corpo.erro, corpo.execucao, bool(dry))
    except Exception:
        logger.exception("Falha a avisar de um fluxo do n8n")
        raise HTTPException(status_code=502, detail="Falha a avisar.")
