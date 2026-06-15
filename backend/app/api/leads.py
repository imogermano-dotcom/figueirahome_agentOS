import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import require_auth
from app.db.supabase_client import get_supabase
from app.models.lead import LeadCreate, LeadUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])

TABLE = "agente_leads"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _run(fn):
    return await asyncio.get_event_loop().run_in_executor(None, fn)


@router.get("/leads")
async def listar_leads(
    estado: Optional[str] = Query(None),
    cliente_id: Optional[UUID] = Query(None),
    imovel_id: Optional[UUID] = Query(None),
):
    def _fetch():
        q = (
            get_supabase()
            .table(TABLE)
            .select("*, agente_clientes(nome, telefone)")
            .order("criado_em", desc=True)
        )
        if estado:
            q = q.eq("estado", estado)
        if cliente_id:
            q = q.eq("cliente_id", str(cliente_id))
        if imovel_id:
            q = q.eq("imovel_id", str(imovel_id))
        return q.execute()

    resp = await _run(_fetch)
    return resp.data


@router.get("/leads/{lead_id}")
async def obter_lead(lead_id: UUID):
    def _fetch():
        return (
            get_supabase()
            .table(TABLE)
            .select("*, agente_clientes(nome, telefone)")
            .eq("id", str(lead_id))
            .single()
            .execute()
        )

    try:
        resp = await _run(_fetch)
        return resp.data
    except Exception:
        raise HTTPException(status_code=404, detail="Lead não encontrado.")


@router.post("/leads", status_code=201)
async def criar_lead(body: LeadCreate):
    def _insert():
        data = body.model_dump(exclude_none=True)
        for f in ("cliente_id", "imovel_id"):
            if f in data:
                data[f] = str(data[f])
        data["criado_em"] = _now()
        data["atualizado_em"] = _now()
        return get_supabase().table(TABLE).insert(data).execute()

    resp = await _run(_insert)
    return resp.data[0] if resp.data else {}


@router.put("/leads/{lead_id}")
async def atualizar_lead(lead_id: UUID, body: LeadUpdate):
    def _update():
        data = body.model_dump(exclude_none=True)
        for f in ("cliente_id", "imovel_id"):
            if f in data:
                data[f] = str(data[f])
        data["atualizado_em"] = _now()
        return get_supabase().table(TABLE).update(data).eq("id", str(lead_id)).execute()

    resp = await _run(_update)
    if not resp.data:
        raise HTTPException(status_code=404, detail="Lead não encontrado.")
    return resp.data[0]


@router.delete("/leads/{lead_id}", status_code=204)
async def apagar_lead(lead_id: UUID):
    def _delete():
        return get_supabase().table(TABLE).delete().eq("id", str(lead_id)).execute()

    await _run(_delete)
