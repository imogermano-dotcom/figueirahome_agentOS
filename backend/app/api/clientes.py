import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import require_auth
from app.db.supabase_client import get_supabase
from app.models.cliente import Cliente, ClienteCreate, ClienteUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])

TABLE = "agente_clientes"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _run(fn):
    return await asyncio.get_event_loop().run_in_executor(None, fn)


@router.get("/clientes")
async def listar_clientes(
    search: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    zona: Optional[str] = Query(None),
    origem: Optional[str] = Query(None),
):
    def _fetch():
        q = get_supabase().table(TABLE).select("*").order("criado_em", desc=True)
        if search:
            q = q.ilike("nome", f"%{search}%")
        if tipo:
            q = q.eq("tipo_interesse", tipo)
        if zona:
            q = q.ilike("zona_preferida", f"%{zona}%")
        if origem:
            q = q.eq("origem", origem)
        return q.execute()

    resp = await _run(_fetch)
    return resp.data


@router.get("/clientes/{cliente_id}")
async def obter_cliente(cliente_id: UUID):
    def _fetch():
        return get_supabase().table(TABLE).select("*").eq("id", str(cliente_id)).single().execute()

    try:
        resp = await _run(_fetch)
        return resp.data
    except Exception:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")


@router.post("/clientes", status_code=201)
async def criar_cliente(body: ClienteCreate):
    def _insert():
        data = body.model_dump(exclude_none=True)
        data["criado_em"] = _now()
        data["atualizado_em"] = _now()
        return get_supabase().table(TABLE).insert(data).execute()

    resp = await _run(_insert)
    return resp.data[0] if resp.data else {}


@router.put("/clientes/{cliente_id}")
async def atualizar_cliente(cliente_id: UUID, body: ClienteUpdate):
    def _update():
        data = body.model_dump(exclude_none=True)
        data["atualizado_em"] = _now()
        return get_supabase().table(TABLE).update(data).eq("id", str(cliente_id)).execute()

    resp = await _run(_update)
    if not resp.data:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    return resp.data[0]


@router.delete("/clientes/{cliente_id}", status_code=204)
async def apagar_cliente(cliente_id: UUID):
    def _delete():
        return get_supabase().table(TABLE).delete().eq("id", str(cliente_id)).execute()

    await _run(_delete)
