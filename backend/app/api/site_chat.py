"""Chat público do figueirahome.pt — visitante anónimo, sem login.

Sem `require_auth` (é para visitante anónimo) nem `X-Automacao-Secret` — mas
não é "sem segredo nenhum": `require_widget_key` (2026-09-01) exige
`X-Widget-Key`, enviado pelo Worker que faz proxy do widget, não pelo
browser do visitante. Três decisões, ver `docs/fases/webchat-site-plano.md`:

1. Sem campo `agente` no pedido. `api/broker.py` teve `require_auth`
   acrescentado a 2026-08-31 precisamente porque deixava o chamador escolher
   o assistente, e um `agente="broker"` não autenticado lia
   `consultar_clientes`/`consultar_leads`. Aqui o router decide sempre.
2. Limite de tamanho e de pedidos por participante: sem isto, tráfego
   avulso esgota crédito da API Anthropic à conta da agência.
3. `X-Widget-Key`: CORS trava o browser, não trava um `curl` directo à
   internet. A chave é a segunda camada, contra bots genéricos — não contra
   alguém disposto a ler o Worker.
"""

import logging
import time
from collections import deque

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agents.broker.engine import responder
from app.api.deps import require_widget_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/site", dependencies=[Depends(require_widget_key)])

_MAX_MENSAGEM = 2000
_JANELA_SEGUNDOS = 300
_MAX_PEDIDOS_NA_JANELA = 15

# ponytail: limitador em memória, por processo -- aceitável com a 1 máquina
# Fly do estado actual (CLAUDE.md). Sobe para Supabase/Redis se algum dia
# houver mais de uma: cada máquina conta à parte e o limite efectivo
# multiplica sem avisar.
_pedidos: dict[str, deque] = {}


def _excedeu_limite(participante: str) -> bool:
    agora = time.monotonic()
    fila = _pedidos.setdefault(participante, deque())
    while fila and agora - fila[0] > _JANELA_SEGUNDOS:
        fila.popleft()
    if len(fila) >= _MAX_PEDIDOS_NA_JANELA:
        return True
    fila.append(agora)
    return False


class SiteChatRequest(BaseModel):
    participante: str = Field(min_length=1, max_length=100)
    mensagem: str = Field(min_length=1, max_length=_MAX_MENSAGEM)


class SiteChatResponse(BaseModel):
    resposta: str


@router.post("/chat", response_model=SiteChatResponse)
async def site_chat(body: SiteChatRequest):
    if _excedeu_limite(body.participante):
        raise HTTPException(status_code=429, detail="Demasiados pedidos. Aguarda um pouco.")

    try:
        resposta = await responder(
            canal="site",
            participante=body.participante,
            mensagem=body.mensagem,
        )
    except Exception:
        logger.exception("Erro no chat do site")
        raise HTTPException(status_code=500, detail="Erro interno do assistente.")

    return SiteChatResponse(resposta=resposta)
