"""Semeadura da conversa de uma lead da Meta, chamada pelo n8n.

Porquê um endpoint e não deixar a lead cair no webhook normal: uma resposta a
um template é quase sempre "Sim", "Olá" ou "Quero saber mais", e o router
(`router._A1_RE`) não reconhece nenhuma delas — a conversa iria para o A2, que
é a recepção. Semear a thread com `agente='a1_vendedor'` antes da resposta
resolve isso pelo mecanismo que já existe (routing sticky, `router.py:73`) e
deixa o texto do template no histórico, para o A1 não repetir o que já foi dito.

O Make escreve em `leads` directamente pelo PostgREST; este módulo não ingere,
só semeia. Chamado com `X-Automacao-Secret`.
"""

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.agents.broker.conversation import save_conversation
from app.agents.broker.guards import (
    campos_mql_da_ficha,
    find_or_create_cliente,
    normalizar_telefone,
)
from app.api.deps import require_automacao_access
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", dependencies=[Depends(require_automacao_access)])

# Só leads de compra/arrendamento vão para o A1. Angariação continua com a
# consultora ao telefone — o A4 está adiado e o router manda angariação para o
# A2 (ver `router._ADIADO_RE`).
_TIPOS_A1 = frozenset({"compra", "arrendamento"})

class ConversaSemeada(BaseModel):
    template: str


async def _run(fn):
    return await asyncio.get_event_loop().run_in_executor(None, fn)


@router.post("/leads/{lead_id}/conversa-semeada")
async def semear_conversa(lead_id: str, corpo: ConversaSemeada):
    """Cria cliente e thread do A1 para uma lead que já recebeu o template."""

    def _fetch():
        return get_supabase().table("leads").select("*").eq("id", lead_id).limit(1).execute()

    resp = await _run(_fetch)
    if not resp.data:
        raise HTTPException(status_code=404, detail="Lead não encontrada.")
    lead = resp.data[0]

    if lead.get("tipo") not in _TIPOS_A1:
        raise HTTPException(
            status_code=422,
            detail=f"Lead de tipo '{lead.get('tipo')}' não é seguida pelo A1.",
        )

    telefone = normalizar_telefone(lead.get("telefone"))
    if not telefone:
        raise HTTPException(status_code=422, detail="Lead sem telefone utilizável.")

    # Idempotente: o n8n pode repetir a chamada sem duplicar a thread nem
    # reescrever o histórico de uma conversa que já esteja a decorrer.
    if lead.get("conversa_id"):
        return {
            "lead_id": lead_id,
            "cliente_id": lead.get("cliente_id"),
            "conversa_id": lead["conversa_id"],
            "ja_existia": True,
        }

    cliente = await find_or_create_cliente(
        nome=lead.get("nome"),
        telefone=telefone,
        email=lead.get("email"),
        origem="meta_ads",
        **campos_mql_da_ficha(lead.get("ficha")),
    )

    # O template é uma mensagem nossa: entra como `assistant` para o A1 o ler
    # como algo que já disse, e não voltar a cumprimentar.
    agora = datetime.now(timezone.utc).isoformat()
    conversa_id = await save_conversation(
        None,
        "whatsapp",
        telefone,
        [{"role": "assistant", "content": corpo.template, "timestamp": agora}],
        "a1_vendedor",
    )

    def _atualizar():
        return get_supabase().table("leads").update({
            "estado": "contactada",
            "cliente_id": cliente.get("id") if cliente else None,
            "conversa_id": conversa_id,
            "atualizado_em": agora,
        }).eq("id", lead_id).execute()

    await _run(_atualizar)
    logger.info("Lead %s semeada (conversa %s)", lead_id, conversa_id)

    return {
        "lead_id": lead_id,
        "cliente_id": cliente.get("id") if cliente else None,
        "conversa_id": conversa_id,
        "ja_existia": False,
    }
