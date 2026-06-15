import uuid
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents.broker.claude_agent import get_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


class BrokerChatRequest(BaseModel):
    mensagem: str
    participante: str = "web_user"


class BrokerChatResponse(BaseModel):
    resposta: str
    participante: str


@router.post("/broker/chat", response_model=BrokerChatResponse)
async def broker_chat(body: BrokerChatRequest):
    if not body.mensagem.strip():
        raise HTTPException(status_code=400, detail="Mensagem não pode estar vazia.")

    try:
        resposta = await get_response(
            participante=body.participante,
            canal="web",
            mensagem_user=body.mensagem,
        )
    except Exception:
        logger.exception("Erro no broker chat")
        raise HTTPException(status_code=500, detail="Erro interno do agente broker.")

    return BrokerChatResponse(resposta=resposta, participante=body.participante)
