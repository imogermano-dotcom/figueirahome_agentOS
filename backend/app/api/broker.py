import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents.broker.engine import responder

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


class BrokerChatRequest(BaseModel):
    mensagem: str
    participante: str = "web_user"
    # None deixa o router decidir — é assim que o painel testa o roteamento.
    agente: str | None = None


class BrokerChatResponse(BaseModel):
    resposta: str
    participante: str


@router.post("/broker/chat", response_model=BrokerChatResponse)
async def broker_chat(body: BrokerChatRequest):
    if not body.mensagem.strip():
        raise HTTPException(status_code=400, detail="Mensagem não pode estar vazia.")

    try:
        resposta = await responder(
            canal="web",
            participante=body.participante,
            mensagem=body.mensagem,
            agente=body.agente,
        )
    except Exception:
        logger.exception("Erro no chat do painel")
        raise HTTPException(status_code=500, detail="Erro interno do assistente.")

    return BrokerChatResponse(resposta=resposta, participante=body.participante)
