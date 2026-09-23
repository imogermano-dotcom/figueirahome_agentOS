import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_auth, require_automacao_access
from app.site_uptime import verificar_site
from app.uptimerobot import estado_site

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.post("/site/uptime-check")
async def uptime_check_endpoint(acesso=Depends(require_automacao_access)):
    try:
        return await verificar_site()
    except Exception:
        logger.exception("Falha a correr o uptime check do site")
        raise HTTPException(status_code=502, detail="Falha a correr o uptime check.")


@router.get("/site/uptime-status")
async def uptime_status_endpoint(acesso=Depends(require_auth)):
    """Lido pelo painel (Dashboard) — vem do UptimeRobot, não do nosso cron
    (desactivado 23/09, redundante com o que o utilizador já tinha)."""
    return await estado_site()
