import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import require_auth
from app.db.supabase_client import get_supabase
from app.models.tarefa import TarefaCreate, TarefaUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])

TABLE = "agente_tarefas"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _run(fn):
    return await asyncio.get_event_loop().run_in_executor(None, fn)


@router.get("/tarefas")
async def listar_tarefas(
    estado: Optional[str] = Query(None),
    responsavel: Optional[str] = Query(None),
    imovel_ref: Optional[str] = Query(None),
):
    def _fetch():
        q = get_supabase().table(TABLE).select("*").order("criado_em", desc=True)
        if estado:
            q = q.eq("estado", estado)
        if responsavel:
            q = q.eq("responsavel", responsavel)
        if imovel_ref:
            q = q.eq("imovel_ref", imovel_ref)
        return q.execute()

    resp = await _run(_fetch)
    return resp.data


@router.get("/tarefas/{tarefa_id}")
async def obter_tarefa(tarefa_id: UUID):
    def _fetch():
        return get_supabase().table(TABLE).select("*").eq("id", str(tarefa_id)).single().execute()

    try:
        resp = await _run(_fetch)
        return resp.data
    except Exception:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")


@router.post("/tarefas", status_code=201)
async def criar_tarefa(body: TarefaCreate):
    def _insert():
        data = body.model_dump(exclude_none=True, mode="json")
        data["criado_em"] = _now()
        data["atualizado_em"] = _now()
        return get_supabase().table(TABLE).insert(data).execute()

    resp = await _run(_insert)
    return resp.data[0] if resp.data else {}


@router.put("/tarefas/{tarefa_id}")
async def atualizar_tarefa(tarefa_id: UUID, body: TarefaUpdate):
    def _update():
        data = body.model_dump(exclude_none=True, mode="json")
        data["atualizado_em"] = _now()
        return get_supabase().table(TABLE).update(data).eq("id", str(tarefa_id)).execute()

    resp = await _run(_update)
    if not resp.data:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    return resp.data[0]


@router.delete("/tarefas/{tarefa_id}", status_code=204)
async def apagar_tarefa(tarefa_id: UUID):
    def _delete():
        return get_supabase().table(TABLE).delete().eq("id", str(tarefa_id)).execute()

    await _run(_delete)
