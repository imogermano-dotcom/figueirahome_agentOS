from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class TarefaBase(BaseModel):
    titulo: str
    descricao: Optional[str] = None
    imovel_ref: Optional[str] = None
    estado: str = "pendente"  # 'pendente' | 'em_curso' | 'concluida' | 'cancelada'
    prazo: Optional[date] = None
    responsavel: Optional[str] = None


class TarefaCreate(TarefaBase):
    pass


class TarefaUpdate(BaseModel):
    titulo: Optional[str] = None
    descricao: Optional[str] = None
    imovel_ref: Optional[str] = None
    estado: Optional[str] = None
    prazo: Optional[date] = None
    responsavel: Optional[str] = None


class Tarefa(TarefaBase):
    id: UUID
    criado_em: datetime
    atualizado_em: datetime

    model_config = {"from_attributes": True}
