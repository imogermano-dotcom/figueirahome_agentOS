"""CRUD de leads para o painel — tabela `leads`.

Apontava para `agente_leads` até 2026-08-18. A troca não é arrumação: o painel
mostrava 2 linhas de teste enquanto **119 leads pagas da Meta** viviam em
`leads`, invisíveis. Ninguém dera por isso porque o caminho do WhatsApp é
automático — mas as que recusam contacto por WhatsApp não têm caminho nenhum,
e sem esta página não há onde as ver para lhes telefonar.

Nome e telefone vêm da própria linha **ou** do cliente ligado, nunca só de um:
as leads da Meta trazem contacto no formulário e nunca chegam a ter
`cliente_id`; as que nascem numa conversa é ao contrário. `cliente_id` tem FK a
`agente_clientes`, portanto o embed do PostgREST continua a funcionar.
"""

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

TABLE = "leads"
_SELECT = "*, agente_clientes(nome, telefone)"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _run(fn):
    return await asyncio.get_event_loop().run_in_executor(None, fn)


def _com_contacto(lead: dict) -> dict:
    """Resolve nome/telefone para o painel não ter de conhecer as duas origens.

    A linha manda: se a lead trouxe contacto do formulário, é esse que vale. O
    cliente ligado é o recurso para as leads nascidas numa conversa, onde o
    contacto vive em `agente_clientes`.
    """
    cliente = lead.get("agente_clientes") or {}
    lead["nome_display"] = lead.get("nome") or cliente.get("nome")
    lead["telefone_display"] = lead.get("telefone") or cliente.get("telefone")
    return lead


@router.get("/leads")
async def listar_leads(
    estado: Optional[str] = Query(None),
    origem: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    cliente_id: Optional[UUID] = Query(None),
    imovel_ref: Optional[str] = Query(None),
):
    def _fetch():
        q = get_supabase().table(TABLE).select(_SELECT).order("criado_em", desc=True)
        if estado:
            q = q.eq("estado", estado)
        if origem:
            q = q.eq("origem", origem)
        if tipo:
            q = q.eq("tipo", tipo)
        if cliente_id:
            q = q.eq("cliente_id", str(cliente_id))
        if imovel_ref:
            q = q.eq("imovel_ref", imovel_ref)
        return q.execute()

    resp = await _run(_fetch)
    return [_com_contacto(lead) for lead in resp.data]


@router.get("/leads/{lead_id}")
async def obter_lead(lead_id: UUID):
    def _fetch():
        return (
            get_supabase()
            .table(TABLE)
            .select(_SELECT)
            .eq("id", str(lead_id))
            .single()
            .execute()
        )

    try:
        resp = await _run(_fetch)
        return _com_contacto(resp.data)
    except Exception:
        raise HTTPException(status_code=404, detail="Lead não encontrado.")


@router.post("/leads", status_code=201)
async def criar_lead(body: LeadCreate):
    def _insert():
        data = body.model_dump(exclude_none=True)
        if "cliente_id" in data:
            data["cliente_id"] = str(data["cliente_id"])
        data["criado_em"] = _now()
        data["atualizado_em"] = _now()
        return get_supabase().table(TABLE).insert(data).execute()

    resp = await _run(_insert)
    return resp.data[0] if resp.data else {}


@router.put("/leads/{lead_id}")
async def atualizar_lead(lead_id: UUID, body: LeadUpdate):
    def _update():
        data = body.model_dump(exclude_none=True)
        if "cliente_id" in data:
            data["cliente_id"] = str(data["cliente_id"])
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
