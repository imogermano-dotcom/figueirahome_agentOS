import asyncio

from fastapi import APIRouter, Depends, HTTPException

from app import leads_para_ego
from app.api.deps import require_automacao_access, require_n8n_access

router = APIRouter(prefix="/api")


# Cron (`crons/schedules.json`, leads-compra-para-ego). Desligado enquanto `LEAD_COMPRA_EGO_DESDE` estiver vazio.
@router.post("/leads/meta/para-ego")
async def leads_para_ego_agora(acesso=Depends(require_automacao_access)):
    resultado = await asyncio.get_event_loop().run_in_executor(None, leads_para_ego.processar)
    if resultado.get("erros"):  # o cron (curl -f) falha à vista; as leads ficam por marcar e repetem
        raise HTTPException(status_code=502, detail=resultado)
    return resultado


# n8n, ramo "Recusou o WhatsApp?" do fluxo de envio da compra: cria a lead no eGO a par do email.
@router.post("/leads/meta/{meta_lead_id}/recusou-whatsapp")
async def lead_recusou_whatsapp(meta_lead_id: str, acesso=Depends(require_n8n_access)):
    resultado = await asyncio.get_event_loop().run_in_executor(None, leads_para_ego.recusou_whatsapp, meta_lead_id)
    if resultado is None:
        raise HTTPException(status_code=404, detail="Contacto não encontrado.")
    return resultado
