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


# n8n, fluxo "Meta leads to supabase", logo a seguir ao RPC da compra: cria a lead no eGO à entrada (pedido #17).
# Não cria por falta de email ou de consultora → 502, para o n8n avisar (a lead fica por criar).
@router.post("/leads/meta/{meta_lead_id}/entrada")
async def lead_entrada(meta_lead_id: str, imovel_ref: str | None = None, whatsapp_optin: str | None = None,
                       acesso=Depends(require_n8n_access)):
    resultado = await asyncio.get_event_loop().run_in_executor(None, leads_para_ego.entrada_meta, meta_lead_id, imovel_ref, whatsapp_optin)
    if resultado is None:
        raise HTTPException(status_code=404, detail="Contacto não encontrado.")
    if resultado["resultado"] in ("sem_email", "sem_consultora"):
        raise HTTPException(status_code=502, detail=resultado)
    return resultado


# n8n, ramo "Recusou o WhatsApp?" do fluxo de envio da compra: cria a lead no eGO a par do email.
@router.post("/leads/meta/{meta_lead_id}/recusou-whatsapp")
async def lead_recusou_whatsapp(meta_lead_id: str, imovel_ref: str | None = None, acesso=Depends(require_n8n_access)):
    resultado = await asyncio.get_event_loop().run_in_executor(None, leads_para_ego.recusou_whatsapp, meta_lead_id, imovel_ref)
    if resultado is None:
        raise HTTPException(status_code=404, detail="Contacto não encontrado.")
    return resultado
