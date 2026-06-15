import asyncio
import logging

from fastapi import Header, HTTPException
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)


async def require_auth(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Não autenticado.")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Não autenticado.")
    supabase = get_supabase()
    loop = asyncio.get_event_loop()
    try:
        resp = await loop.run_in_executor(None, lambda: supabase.auth.get_user(token))
        if not resp.user:
            raise HTTPException(status_code=401, detail="Token inválido.")
        return resp.user
    except HTTPException:
        raise
    except Exception:
        logger.warning("Falha na validação do token auth.")
        raise HTTPException(status_code=401, detail="Token inválido.")
