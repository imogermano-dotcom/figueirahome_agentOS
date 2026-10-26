import asyncio
import json
import logging
from datetime import date, datetime, timedelta, timezone

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


def reconciliar_propostas() -> dict:
    """Corrige `estado_proposta` das oportunidades cuja proposta mudou no eGO sem a oportunidade ser editada (pedido #34).
    Só toca no estado e só em linhas que já o têm; as que a API conhece e o Supabase não (proposta nova por ler) só
    se contam, o valor e a data vêm do relatório."""
    api = ego_api.estados_de_proposta()
    sb = get_supabase()
    atuais: dict[str, str | None] = {}
    refs = list(api)
    for i in range(0, len(refs), 50):
        r = sb.table("oportunidades").select("oportunidade_ref,estado_proposta").in_("oportunidade_ref", refs[i:i + 50]).execute()
        atuais.update({x["oportunidade_ref"]: x["estado_proposta"] for x in r.data})
    corrigidas, por_ler = [], 0
    for ref, estado in api.items():
        antigo = atuais.get(ref)
        if antigo is None:
            por_ler += 1
        elif antigo != estado:
            sb.table("oportunidades").update({"estado_proposta": estado}).eq("oportunidade_ref", ref).eq("estado_proposta", antigo).execute()
            corrigidas.append(f"{ref}: {antigo} → {estado}")
    return {"na_api": len(api), "corrigidas": corrigidas, "por_ler": por_ler}


_JANELA_APAGADAS_DIAS = 90
_LIMITE_APAGADAS = 100  # chamadas ao eGO por volta; o resto fica para o dia seguinte


def reconciliar_apagadas(hoje: date | None = None) -> dict:
    """Marca `apagada_no_ego` nas oportunidades apagadas no eGO e desmarca as que voltaram (pedido #31, migration 0054).

    O sync só lê as «editadas nas últimas 48 h» e uma apagada nunca mais aparece, por isso ficava «Ativa» para sempre e bloqueava a
    criação de leads dessa pessoa. Faltar na lista ativa NÃO chega (as arquivadas também faltam): cada candidata é confirmada com
    o `GetOpportunity` (`fieldStatusId = 1` ou 404). Candidatas: editadas nos últimos 90 dias, não marcadas, fora da lista ativa."""
    ativas = ego_api.refs_ativas()
    sb = get_supabase()
    desde = ((hoje or date.today()) - timedelta(days=_JANELA_APAGADAS_DIAS)).isoformat()
    candidatas, inicio = [], 0
    while True:  # ordenado: sem `order` a paginação do PostgREST salta e repete linhas
        lote = (sb.table("oportunidades").select("oportunidade_ref,url,apagada_no_ego").gte("ego_editado_em", desde)
                .order("oportunidade_ref").range(inicio, inicio + 999).execute().data)
        candidatas += lote
        inicio += 1000
        if len(lote) < 1000:
            break
    por_confirmar = [r for r in candidatas if not r.get("apagada_no_ego") and r["oportunidade_ref"] not in ativas and r.get("url")]
    voltaram = [r for r in candidatas if r.get("apagada_no_ego") and r["oportunidade_ref"] in ativas]
    resumo = {"candidatas": len(por_confirmar), "marcadas": [], "desmarcadas": [], "adiadas": 0, "erros": 0}
    for r in voltaram:
        sb.table("oportunidades").update({"apagada_no_ego": False, "apagada_em": None}).eq("oportunidade_ref", r["oportunidade_ref"]).execute()
        resumo["desmarcadas"].append(r["oportunidade_ref"])
    resumo["adiadas"] = max(0, len(por_confirmar) - _LIMITE_APAGADAS)
    for r in por_confirmar[:_LIMITE_APAGADAS]:
        try:
            if ego_api.oportunidade_apagada(r["url"].rstrip("/").rsplit("/", 1)[1]):
                sb.table("oportunidades").update({"apagada_no_ego": True, "apagada_em": datetime.now(timezone.utc).isoformat()}) \
                    .eq("oportunidade_ref", r["oportunidade_ref"]).execute()
                resumo["marcadas"].append(r["oportunidade_ref"])
        except Exception:
            logger.exception("Falha a confirmar a oportunidade %s", r["oportunidade_ref"])
            resumo["erros"] += 1
    return resumo


@router.post("/oportunidades/sync/propostas")
async def sync_propostas_endpoint(acesso=Depends(require_sync_access)):
    """Passo diário depois do sync das oportunidades: corrige o estado das propostas pela API do eGO e marca as oportunidades
    apagadas (`apagadas` no resumo). Cada parte corre à parte: a falha de uma não esconde a outra."""
    origem = "cron" if acesso == "sync-secret" else "manual"
    loop = asyncio.get_event_loop()
    resumo: dict = {}
    falhas: list[str] = []
    try:
        resumo = await loop.run_in_executor(None, reconciliar_propostas)
    except Exception as e:
        logger.exception("Falha na reconciliação das propostas")
        falhas.append(f"propostas: {e!r}")
    try:
        resumo["apagadas"] = await loop.run_in_executor(None, reconciliar_apagadas)
    except Exception as e:
        logger.exception("Falha na reconciliação das oportunidades apagadas")
        falhas.append(f"apagadas: {e!r}")
    if falhas:
        await falha_de_sync("egorealestate_propostas", "propostas e oportunidades apagadas", origem, "; ".join(falhas))
        if len(falhas) == 2:
            raise HTTPException(status_code=502, detail="Falha a reconciliar as propostas e as oportunidades apagadas.")
        resumo["falhas"] = falhas
    await _log_execucao(resumo, origem, tipo="egorealestate_propostas")
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
