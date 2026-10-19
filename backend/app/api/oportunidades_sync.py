import asyncio
import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_auth, require_sync_access
from app.config import settings
from app.integrations import ego_api
from app.notificacoes import falha_de_sync
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


async def _log_execucao(resumo: dict, origem: str, tipo: str = "egorealestate_oportunidades_completo") -> None:
    def _insert():
        return get_supabase().table("agente_sync_log").insert({
            "tipo": tipo, "resumo": resumo, "origem": origem,
        }).execute()

    await asyncio.get_event_loop().run_in_executor(None, _insert)


# O scraper levanta isto quando, depois de aplicar o filtro «Últimas 48 horas», o eGO não mostra o botão Relatórios.
_SEM_RESULTADOS = 'Link "Relatórios" não encontrado'


async def _sem_alteracoes(texto_do_erro: str) -> bool:
    """Esse erro é «0 resultados» ou uma falha de navegação? Pergunta à API do eGO. Sem conseguir confirmar,
    continua a ser falha (um aviso a mais custa menos do que um sync partido em silêncio)."""
    try:  # o erro chega como JSON ({"detail": "..."}), com as aspas escapadas: compara-se com o detalhe já lido
        detalhe = str(json.loads(texto_do_erro).get("detail", ""))
    except (ValueError, AttributeError):
        detalhe = texto_do_erro
    if _SEM_RESULTADOS not in detalhe:
        return False
    try:
        editadas = await asyncio.get_event_loop().run_in_executor(None, ego_api.oportunidades_editadas_desde, 48)
    except Exception:
        logger.exception("Não consegui confirmar pela API se há oportunidades editadas nas últimas 48 h")
        return False
    return editadas == 0


@router.post("/oportunidades/sync/completo")
async def sync_oportunidades_completo_endpoint(acesso=Depends(require_sync_access)):
    origem = "cron" if acesso == "sync-secret" else "manual"
    if not settings.scraper_service_url or not settings.scraper_service_secret:
        raise HTTPException(status_code=502, detail="SCRAPER_SERVICE_URL/SECRET não configurados.")

    try:
        async with httpx.AsyncClient(timeout=240) as client:
            resp = await client.post(
                f"{settings.scraper_service_url}/run/oportunidades-completo",
                headers={"X-Scraper-Secret": settings.scraper_service_secret},
            )
            resp.raise_for_status()
            resumo = resp.json()
    except httpx.HTTPStatusError as e:
        if await _sem_alteracoes(e.response.text):
            logger.info("Sync de oportunidades: 0 edições nas últimas 48 h (confirmado pela API), nada a gravar")
            resumo = {"sem_alteracoes": True, "motivo": "0 oportunidades editadas nas últimas 48 h (confirmado pela API do eGO)"}
        else:
            logger.exception("Scraper devolveu erro no sync de oportunidades (relatório completo)")
            await falha_de_sync("egorealestate_oportunidades_completo", "oportunidades", origem, e.response.text)
            raise HTTPException(status_code=502, detail=e.response.text)
    except Exception as e:
        logger.exception("Falha ao contactar o serviço de scraping de oportunidades")
        await falha_de_sync("egorealestate_oportunidades_completo", "oportunidades", origem, repr(e))
        raise HTTPException(status_code=502, detail="Falha ao contactar o serviço de scraping.")

    await _log_execucao(resumo, origem)
    return resumo


@router.post("/oportunidades/sync/tarefas")
async def sync_tarefas_endpoint(acesso=Depends(require_sync_access)):
    """Snapshot das tarefas activas do eGO (4 relatórios em fatias, ~150 s no PC;
    tecto de 600 s para o Fly). Mesmo desenho do `completo`: o backend guarda o
    segredo do scraper e grava o resumo em `agente_sync_log`."""
    origem = "cron" if acesso == "sync-secret" else "manual"
    if not settings.scraper_service_url or not settings.scraper_service_secret:
        raise HTTPException(status_code=502, detail="SCRAPER_SERVICE_URL/SECRET não configurados.")

    try:
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.post(
                f"{settings.scraper_service_url}/run/tarefas",
                headers={"X-Scraper-Secret": settings.scraper_service_secret},
            )
            resp.raise_for_status()
            resumo = resp.json()
    except httpx.HTTPStatusError as e:
        logger.exception("Scraper devolveu erro no sync de tarefas")
        await falha_de_sync("egorealestate_tarefas", "tarefas", origem, e.response.text)
        raise HTTPException(status_code=502, detail=e.response.text)
    except Exception as e:
        logger.exception("Falha ao contactar o serviço de scraping de tarefas")
        await falha_de_sync("egorealestate_tarefas", "tarefas", origem, repr(e))
        raise HTTPException(status_code=502, detail="Falha ao contactar o serviço de scraping.")

    await _log_execucao(resumo, origem, tipo="egorealestate_tarefas")
    return resumo


@router.get("/oportunidades/sync/log", dependencies=[Depends(require_auth)])
async def oportunidades_sync_log_endpoint(limit: int = 20):
    def _fetch():
        return (
            get_supabase()
            .table("agente_sync_log")
            .select("*")
            .eq("tipo", "egorealestate_oportunidades_completo")
            .order("executado_em", desc=True)
            .limit(limit)
            .execute()
        )

    resp = await asyncio.get_event_loop().run_in_executor(None, _fetch)
    return resp.data
