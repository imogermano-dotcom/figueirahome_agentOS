from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID


class ChamadaBase(BaseModel):
    cliente_id: Optional[UUID] = None
    call_control_id: Optional[str] = None
    numero_origem: Optional[str] = None
    duracao: Optional[int] = None
    transcricao: Optional[str] = None
    resumo_ia: Optional[str] = None
    gravacao_url: Optional[str] = None


class ChamadaCreate(ChamadaBase):
    pass


class Chamada(ChamadaBase):
    id: UUID
    data_hora: datetime

    model_config = {"from_attributes": True}
