from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID


class ClienteBase(BaseModel):
    nome: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None
    tipo_interesse: Optional[str] = None  # 'compra' | 'arrendamento' | 'venda' | 'outro'
    orcamento: Optional[float] = None
    zona_preferida: Optional[str] = None
    notas: Optional[str] = None
    origem: Optional[str] = None  # 'chamada' | 'manual' | 'chat'


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(ClienteBase):
    pass


class Cliente(ClienteBase):
    id: UUID
    criado_em: datetime
    atualizado_em: datetime

    model_config = {"from_attributes": True}
