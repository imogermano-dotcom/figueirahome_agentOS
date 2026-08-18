"""Lead não qualificada, de qualquer origem — tabela `leads` (migration 0021).

Substituiu `agente_leads` a 2026-08-18. A tabela antiga tinha 4 campos úteis
(`cliente_id`, `imovel_id`, `estado`, `notas`) e nenhum contacto próprio: o nome
e o telefone vinham sempre por join a `agente_clientes`. Isso funcionava para as
leads nascidas numa conversa, e deixava as 119 da Meta — que trazem nome e
telefone no formulário e nunca chegam a ter `cliente_id` — invisíveis no painel.

Em `leads` o contacto está na própria linha e `cliente_id` é opcional. Os dois
casos coexistem, e é o painel que decide qual mostrar.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

# União dos dois vocabulários que existiam. O de `leads` (0021) manda porque é
# dele que `guards._ESTADOS_LEAD_ABERTA` depende; `visita` e `proposta` vêm do
# painel antigo e são etapas comerciais reais que não havia razão para perder.
ESTADOS = (
    "nova", "contactada", "qualificada",
    "visita", "proposta",
    "fechada", "perdida", "sem_interesse",
)

# Fechadas para o assistente: uma lead nestes estados não volta a ser reaberta
# nem requalificada (`tools._criar_lead_se_preciso`).
ESTADOS_FECHADOS = ("fechada", "perdida", "sem_interesse")

# Eixo distinto de `tipo` (o interesse: compra | angariacao).
ORIGENS = ("meta", "assistente", "voz", "landing", "manual")


class LeadBase(BaseModel):
    tipo: Optional[str] = None
    estado: Optional[str] = None
    origem: Optional[str] = None

    nome: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None

    imovel_ref: Optional[str] = None
    responsavel: Optional[str] = None
    notas: Optional[str] = None
    cliente_id: Optional[UUID] = None


class LeadCreate(LeadBase):
    estado: str = "nova"
    origem: str = "manual"
    tipo: str = "compra"


class LeadUpdate(LeadBase):
    pass


class Lead(LeadBase):
    id: UUID
    criado_em: datetime
    atualizado_em: datetime

    model_config = {"from_attributes": True}
