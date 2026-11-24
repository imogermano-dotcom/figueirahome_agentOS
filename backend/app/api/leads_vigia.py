import asyncio
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app import vigia_leads
from app.api.deps import require_n8n_access

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


class LeadsDaMeta(BaseModel):
    """Leads por dia (AAAA-MM-DD) segundo a conta de anúncios; o n8n manda os últimos dias."""
    dias: dict[str, int]
    ids: dict[str, list[str]] | None = None  # ids (`leadgen_id`) das leads por dia, se o n8n os listar

    @field_validator("ids")
    @classmethod
    def _ids_validos(cls, v: dict[str, list[str]] | None) -> dict[str, list[str]] | None:
        for dia, lista in (v or {}).items():
            date.fromisoformat(dia)
            if len(lista) > 300 or not all(i.isdigit() and 8 <= len(i) <= 20 for i in lista):
                raise ValueError("ids inválidos")
        return v

    @field_validator("dias")
    @classmethod
    def _dias_validos(cls, v: dict[str, int]) -> dict[str, int]:
        if not v or len(v) > 7:
            raise ValueError("entre 1 e 7 dias")
        for dia, n in v.items():
            date.fromisoformat(dia)
            if n < 0:
                raise ValueError("contagem negativa")
        return v


# n8n, fluxo «Vigia leads Meta» (de 30 em 30 min). `?dry=1` compara sem registar nem avisar.
@router.post("/leads/meta/reconciliar")
async def reconciliar_leads_meta(corpo: LeadsDaMeta, dry: int = 0, acesso=Depends(require_n8n_access)):
    try:
        return await asyncio.get_event_loop().run_in_executor(None, vigia_leads.verificar, corpo.dias, bool(dry), corpo.ids)
    except Exception:
        logger.exception("Falha na reconciliação das leads da Meta")
        raise HTTPException(status_code=502, detail="Falha a reconciliar as leads da Meta.")
