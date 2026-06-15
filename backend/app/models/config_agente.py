from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID


class ConfigAgenteBase(BaseModel):
    persona: Optional[str] = None
    instrucoes: Optional[str] = None
    idioma: str = "pt-PT"
    ativo: bool = True


class ConfigAgenteUpdate(ConfigAgenteBase):
    pass


class ConfigAgente(ConfigAgenteBase):
    id: UUID
    agente: str
    atualizado_em: datetime

    model_config = {"from_attributes": True}
