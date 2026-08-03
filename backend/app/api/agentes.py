"""Observabilidade dos assistentes — métricas e conversas.

A configuração continua em `api/config.py`; isto é o que veio da instrumentação
(migrations 0016/0017).
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import require_auth
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agentes", dependencies=[Depends(require_auth)])


async def _run(fn):
    return await asyncio.get_event_loop().run_in_executor(None, fn)


@router.get("/metricas")
async def metricas(
    agente: str | None = None,
    dias: int = Query(30, ge=1, le=365),
):
    """Métricas agregadas. `agente` omitido = todos."""

    def _fetch():
        return get_supabase().rpc(
            "agente_metricas", {"p_agente": agente, "p_dias": dias}
        ).execute()

    try:
        resp = await _run(_fetch)
    except Exception:
        logger.exception("Erro ao obter métricas do agente %s", agente)
        raise HTTPException(status_code=500, detail="Erro ao obter métricas.")

    return resp.data or {}


@router.get("/conversas")
async def conversas(
    agente: str | None = None,
    limite: int = Query(20, ge=1, le=100),
):
    """Conversas recentes com custo e nº de turnos.

    Duas queries em vez de um join: o PostgREST não agrega filhos, e somar 20
    conversas em Python é mais simples do que uma vista só para isto.
    """

    def _fetch():
        db = get_supabase()
        q = db.table("agente_conversas").select("id,canal,agente,participante,atualizado_em,mensagens")
        if agente:
            q = q.eq("agente", agente)
        convs = q.order("atualizado_em", desc=True).limit(limite).execute().data or []
        if not convs:
            return []

        ids = [c["id"] for c in convs]
        inter = (
            db.table("agente_interacoes")
            .select("conversa_id,custo_usd,latencia_ms,tools_usadas,erro")
            .in_("conversa_id", ids)
            .execute()
            .data
            or []
        )

        agregado: dict[str, dict] = {}
        for i in inter:
            a = agregado.setdefault(
                i["conversa_id"], {"custo_usd": 0.0, "turnos": 0, "erros": 0, "tools": 0}
            )
            a["custo_usd"] += float(i["custo_usd"] or 0)
            a["turnos"] += 1
            a["erros"] += 1 if i["erro"] else 0
            a["tools"] += len(i["tools_usadas"] or [])

        saida = []
        for c in convs:
            mensagens = c.get("mensagens") or []
            saida.append({
                "id": c["id"],
                "canal": c["canal"],
                "agente": c.get("agente"),
                "participante": c["participante"],
                "atualizado_em": c["atualizado_em"],
                "mensagens": len(mensagens),
                # Primeira coisa que o cliente disse — dá para reconhecer a
                # conversa na lista sem a abrir.
                "primeira_mensagem": next(
                    (m.get("content", "")[:120] for m in mensagens if m.get("role") == "user"),
                    "",
                ),
                **agregado.get(c["id"], {"custo_usd": 0.0, "turnos": 0, "erros": 0, "tools": 0}),
            })
        return saida

    try:
        return await _run(_fetch)
    except Exception:
        logger.exception("Erro ao listar conversas do agente %s", agente)
        raise HTTPException(status_code=500, detail="Erro ao listar conversas.")


@router.get("/conversas/{conversa_id}")
async def conversa(conversa_id: str):
    """Transcrição completa + o que cada turno custou."""

    def _fetch():
        db = get_supabase()
        c = (
            db.table("agente_conversas")
            .select("*")
            .eq("id", conversa_id)
            .limit(1)
            .execute()
            .data
        )
        if not c:
            return None
        turnos = (
            db.table("agente_interacoes")
            .select("*")
            .eq("conversa_id", conversa_id)
            .order("criado_em")
            .execute()
            .data
            or []
        )
        return {**c[0], "turnos": turnos}

    try:
        resultado = await _run(_fetch)
    except Exception:
        logger.exception("Erro ao obter conversa %s", conversa_id)
        raise HTTPException(status_code=500, detail="Erro ao obter conversa.")

    if not resultado:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return resultado
