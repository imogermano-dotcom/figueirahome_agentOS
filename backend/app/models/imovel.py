from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel


class ImovelBase(BaseModel):
    imovel_ref: str
    natureza: Optional[str] = None          # 'Apartamento' | 'Moradia' | ...
    disponibilidade: Optional[str] = None   # 'Disponível' | 'Em Prospecção' | 'Por validar' | 'Retirado'
    estado: Optional[str] = None            # condição: 'Novo' | 'Usado' | 'Renovado' | ...
    fonte: str = "manual"                   # 'egorealestate' | 'site_proprio' | 'idealista' | 'imovirtual' | 'manual' | 'csv'

    titulo: Optional[str] = None
    descricao: Optional[str] = None
    proprietario: Optional[str] = None
    angariador: Optional[str] = None
    vendedor: Optional[str] = None

    quartos: Optional[int] = None
    casas_banho: Optional[int] = None
    suites: Optional[int] = None
    piso: Optional[str] = None
    num_pisos: Optional[int] = None
    numero: Optional[str] = None
    fracao: Optional[str] = None

    area_util: Optional[float] = None
    area_bruta: Optional[float] = None
    area_terreno: Optional[float] = None
    conservacao: Optional[str] = None
    certificacao_energetica: Optional[str] = None

    venda_preco: Optional[float] = None
    arrendamento_preco: Optional[float] = None
    comissao_agencia: Optional[float] = None
    comissao_angariador: Optional[float] = None
    comissao_vendedor: Optional[float] = None
    exclusividade: Optional[str] = None

    morada: Optional[str] = None
    codigo_postal: Optional[str] = None
    concelho: Optional[str] = None
    freguesia: Optional[str] = None
    zona: Optional[str] = None

    piscina: Optional[bool] = None
    garagem: Optional[bool] = None
    jardim: Optional[bool] = None
    terraco: Optional[bool] = None
    varanda: Optional[bool] = None
    vista_mar: Optional[bool] = None
    vista_praia: Optional[bool] = None
    ar_condicionado: Optional[bool] = None
    elevador: Optional[bool] = None
    aquecimento_central: Optional[bool] = None
    arrecadacao: Optional[bool] = None
    estacionamento: Optional[bool] = None

    portais: Optional[str] = None
    foto_principal: Optional[str] = None
    fotos: List[str] = []

    ego_id: Optional[int] = None
    ego_atualizado_em: Optional[datetime] = None
    data_criacao: Optional[date] = None
    data_alteracao: Optional[date] = None


class ImovelCreate(ImovelBase):
    pass


class ImovelUpdate(BaseModel):
    """Todos os campos opcionais — update parcial."""

    natureza: Optional[str] = None
    disponibilidade: Optional[str] = None
    estado: Optional[str] = None
    fonte: Optional[str] = None
    titulo: Optional[str] = None
    descricao: Optional[str] = None
    proprietario: Optional[str] = None
    angariador: Optional[str] = None
    vendedor: Optional[str] = None
    quartos: Optional[int] = None
    casas_banho: Optional[int] = None
    suites: Optional[int] = None
    piso: Optional[str] = None
    num_pisos: Optional[int] = None
    numero: Optional[str] = None
    fracao: Optional[str] = None
    area_util: Optional[float] = None
    area_bruta: Optional[float] = None
    area_terreno: Optional[float] = None
    conservacao: Optional[str] = None
    certificacao_energetica: Optional[str] = None
    venda_preco: Optional[float] = None
    arrendamento_preco: Optional[float] = None
    comissao_agencia: Optional[float] = None
    comissao_angariador: Optional[float] = None
    comissao_vendedor: Optional[float] = None
    exclusividade: Optional[str] = None
    morada: Optional[str] = None
    codigo_postal: Optional[str] = None
    concelho: Optional[str] = None
    freguesia: Optional[str] = None
    zona: Optional[str] = None
    piscina: Optional[bool] = None
    garagem: Optional[bool] = None
    jardim: Optional[bool] = None
    terraco: Optional[bool] = None
    varanda: Optional[bool] = None
    vista_mar: Optional[bool] = None
    vista_praia: Optional[bool] = None
    ar_condicionado: Optional[bool] = None
    elevador: Optional[bool] = None
    aquecimento_central: Optional[bool] = None
    arrecadacao: Optional[bool] = None
    estacionamento: Optional[bool] = None
    portais: Optional[str] = None
    foto_principal: Optional[str] = None
    fotos: Optional[List[str]] = None
    ego_id: Optional[int] = None
    ego_atualizado_em: Optional[datetime] = None
    data_alteracao: Optional[date] = None


class Imovel(ImovelBase):
    model_config = {"from_attributes": True}
