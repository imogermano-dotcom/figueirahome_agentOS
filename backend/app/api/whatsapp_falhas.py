import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException

from app.agents.broker.channels.whatsapp import recibos
from app.api.deps import require_automacao_access
from app.notificacoes import _alertas_extra, notificar

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

_HORAS = 24


# Cron diário (`crons/schedules.json`, resumo-falhas-whatsapp). Só manda email quando há falhas.
@router.post("/whatsapp/falhas/resumo")
async def resumo_de_falhas(acesso=Depends(require_automacao_access)):
    loop = asyncio.get_event_loop()
    try:
        falhas = await loop.run_in_executor(None, recibos.falhas_recentes, _HORAS)
    except Exception:
        logger.exception("Falha a ler os números sem WhatsApp")
        raise HTTPException(status_code=502, detail="Falha a ler os números sem WhatsApp.")
    if falhas:
        await loop.run_in_executor(
            None,
            lambda: notificar(
                f"WhatsApp: {len(falhas)} número(s) sem entrega",
                recibos.texto_do_resumo(falhas, _HORAS),
                para_extra=_alertas_extra(),
            ),
        )
    return {"falhas": len(falhas)}
