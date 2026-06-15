from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class ImovelBase(BaseModel):
    referencia: Optional[str] = None
    tipo: Optional[str] = None  # 'apartamento' | 'moradia' | 'terreno' | 'comercial'
    fonte: str = "manual"       # 'idealista' | 'imovirtual' | 'agente_voz' | 'manual' | 'csv'
    localizacao: Optional[str] = None
    preco: Optional[float] = None
    area: Optional[float] = None
    quartos: Optional[int] = None
    descricao: Optional[str] = None
    fotos: List[str] = []
    estado: str = "disponivel"  # 'disponivel' | 'reservado' | 'vendido'


class ImovelCreate(ImovelBase):
    pass


class ImovelUpdate(ImovelBase):
    pass


class Imovel(ImovelBase):
    id: UUID
    criado_em: datetime
    atualizado_em: datetime

    model_config = {"from_attributes": True}
