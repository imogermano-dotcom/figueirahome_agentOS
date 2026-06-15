from .cliente import Cliente, ClienteCreate, ClienteUpdate
from .imovel import Imovel, ImovelCreate, ImovelUpdate
from .lead import Lead, LeadCreate, LeadUpdate
from .chamada import Chamada, ChamadaCreate
from .conversa import Conversa, ConversaCreate
from .config_agente import ConfigAgente, ConfigAgenteUpdate

__all__ = [
    "Cliente", "ClienteCreate", "ClienteUpdate",
    "Imovel", "ImovelCreate", "ImovelUpdate",
    "Lead", "LeadCreate", "LeadUpdate",
    "Chamada", "ChamadaCreate",
    "Conversa", "ConversaCreate",
    "ConfigAgente", "ConfigAgenteUpdate",
]
