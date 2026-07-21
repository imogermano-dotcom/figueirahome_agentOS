import asyncio
import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends

from app.api.deps import require_auth
from app.db.supabase_client import get_supabase, get_supabase_imoveis

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])


async def _run(fn):
    return await asyncio.get_event_loop().run_in_executor(None, fn)


@router.get("/dashboard")
async def dashboard():
    hoje = date.today().isoformat()

    def _fetch():
        db = get_supabase()

        chamadas = (
            db.table("agente_chamadas")
            .select("id", count="exact")
            .gte("data_hora", f"{hoje}T00:00:00+00:00")
            .execute()
        )

        leads_novos = (
            db.table("agente_leads")
            .select("id", count="exact")
            .eq("estado", "novo")
            .execute()
        )

        imoveis_disponiveis = (
            get_supabase_imoveis()
            .table("imoveis")
            .select("imovel_ref", count="exact")
            .eq("disponibilidade", "Disponível")
            .execute()
        )

        conversas_hoje = (
            db.table("agente_conversas")
            .select("id", count="exact")
            .gte("atualizado_em", f"{hoje}T00:00:00+00:00")
            .execute()
        )

        return {
            "chamadas_hoje": chamadas.count or 0,
            "leads_novos": leads_novos.count or 0,
            "imoveis_disponiveis": imoveis_disponiveis.count or 0,
            "conversas_hoje": conversas_hoje.count or 0,
        }

    return await _run(_fetch)
