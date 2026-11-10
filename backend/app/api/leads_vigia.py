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


class FalhaDoVigia(BaseModel):
    erro: str = ""


# n8n, saída de erro do fluxo «Vigia leads Meta»: o vigia falhou (ex.: token da Meta expirado). Email, no máx. 1 por 12 h.
@router.post("/leads/meta/vigia-falhou")
async def vigia_falhou(corpo: FalhaDoVigia, dry: int = 0, acesso=Depends(require_n8n_access)):
    try:
        return await asyncio.get_event_loop().run_in_executor(None, vigia_leads.avisar_falha, corpo.erro, bool(dry))
    except Exception:
        logger.exception("Falha a avisar que o vigia das leads da Meta falhou")
        raise HTTPException(status_code=502, detail="Falha a avisar.")


# n8n, fluxo «Vigia leads Meta» (de 30 em 30 min). `?dry=1` compara sem registar nem avisar.
@router.post("/leads/meta/reconciliar")
async def reconciliar_leads_meta(corpo: LeadsDaMeta, dry: int = 0, acesso=Depends(require_n8n_access)):
    try:
        return await asyncio.get_event_loop().run_in_executor(None, vigia_leads.verificar, corpo.dias, bool(dry))
    except Exception:
        logger.exception("Falha na reconciliação das leads da Meta")
        raise HTTPException(status_code=502, detail="Falha a reconciliar as leads da Meta.")
