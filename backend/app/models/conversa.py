from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID


class ConversaBase(BaseModel):
    canal: str  # 'web' | 'whatsapp' | 'telegram' | 'email'
    participante: Optional[str] = None
    mensagens: List[Any] = []  # [{role, content, timestamp}, ...]


class ConversaCreate(ConversaBase):
    pass


class Conversa(ConversaBase):
    id: UUID
    criado_em: datetime
    atualizado_em: datetime

    model_config = {"from_attributes": True}
