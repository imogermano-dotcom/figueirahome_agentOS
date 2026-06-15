from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID


class LeadBase(BaseModel):
    cliente_id: Optional[UUID] = None
    imovel_id: Optional[UUID] = None
    estado: str = "novo"  # 'novo' | 'contactado' | 'visita' | 'proposta' | 'fechado' | 'perdido'
    notas: Optional[str] = None


class LeadCreate(LeadBase):
    pass


class LeadUpdate(LeadBase):
    pass


class Lead(LeadBase):
    id: UUID
    criado_em: datetime
    atualizado_em: datetime

    model_config = {"from_attributes": True}
