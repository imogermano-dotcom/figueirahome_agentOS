import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_auth
from app.db.supabase_client import get_supabase
from app.models.config_agente import ConfigAgenteUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])

TABLE = "agente_config"
AGENTES_VALIDOS = {"voz", "broker"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _run(fn):
    return await asyncio.get_event_loop().run_in_executor(None, fn)


@router.get("/config/{agente}")
async def obter_config(agente: str):
    if agente not in AGENTES_VALIDOS:
        raise HTTPException(status_code=404, detail="Agente não encontrado.")

    def _fetch():
        return get_supabase().table(TABLE).select("*").eq("agente", agente).single().execute()

    try:
        resp = await _run(_fetch)
        return resp.data
    except Exception:
        raise HTTPException(status_code=404, detail="Config não encontrada.")


@router.put("/config/{agente}")
async def atualizar_config(agente: str, body: ConfigAgenteUpdate):
    if agente not in AGENTES_VALIDOS:
        raise HTTPException(status_code=404, detail="Agente não encontrado.")

    def _update():
        data = body.model_dump(exclude_none=True)
        data["atualizado_em"] = _now()
        return get_supabase().table(TABLE).update(data).eq("agente", agente).execute()

    resp = await _run(_update)
    if not resp.data:
        raise HTTPException(status_code=404, detail="Config não encontrada.")
    return resp.data[0]
